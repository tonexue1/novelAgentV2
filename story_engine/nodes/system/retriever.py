"""Retriever（规则版，无 embedding）—— 对应 docs/nodes/system/retriever.md + ARCHITECTURE §8。

filter-then-rank-then-budget：
  ① 过滤：scope 匹配 + as-of 可见（未来不泄漏）+ 认知边界（剔除 hidden_from 的 secret）。
  ② 排序：salience / recency / 词法相关(BM25) / tier / goal 加权，确定性打分。
  ③ 预算：按分排序贪心填至 token 预算（tiktoken 计数）。
分桶：trajectory / character / streaming（M1 打标签，全局预算；子预算留后续）。
语义检索（embedding）留 M4。
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Literal

from rank_bm25 import BM25Okapi

from story_engine.util.tokens import count_tokens

# 默认打分权重（M1 硬编码，后续可配）
W_SALIENCE = 1.0
W_RECENCY = 0.5
W_FOCUS = 1.5
W_TIER = 0.5
GOAL_BOOST = 0.5

# 优先级分级阈值（MUST 必进 / SHOULD 分桶配额 / MAY 余量兜底）
Priority = Literal["MUST", "SHOULD", "MAY"]
MUST_SALIENCE = 0.85
SHOULD_SALIENCE = 0.5

# 分桶子预算默认权重（占总预算比例）
DEFAULT_BUCKET_WEIGHTS = {"character": 0.4, "trajectory": 0.4, "streaming": 0.2}


def default_priority(it: "RetrievableItem") -> Priority:
    """确定性优先级：目标/知悉的 secret/高显著=MUST；当前场或中显著=SHOULD；余=MAY。"""
    if it.is_goal or it.kind == "arc:secret" or it.salience >= MUST_SALIENCE:
        return "MUST"
    if it.bucket == "streaming" or it.salience >= SHOULD_SALIENCE:
        return "SHOULD"
    return "MAY"

_CJK = r"\u4e00-\u9fff"
_TOKEN_RE = re.compile(rf"[{_CJK}]|[a-zA-Z0-9]+")


def _tokenize(text: str) -> list[str]:
    """CJK 按字、ASCII 按词。"""
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


@dataclass
class Query:
    as_of_chapter: int
    char: str | None = None          # character 节点：全称 char.{slug}，限 scope + 认知边界
    focus: str = ""                  # 场景目标 / 关键词，供词法相关
    budget_tokens: int = 2000
    bucket_weights: dict[str, float] | None = None   # None=默认权重


@dataclass
class RetrievableItem:
    item_id: str
    text: str
    kind: str                        # memory:{type} | arc:{kind}
    scope: str
    t_valid: int
    salience: float
    tier: int | None                 # CharTier 值，arc 为 None
    is_goal: bool = False
    bucket: str = "trajectory"       # trajectory | character | streaming


@dataclass
class RetrievalResult:
    items: list[RetrievableItem] = field(default_factory=list)   # 入选（优先级→分序）
    dropped: list[RetrievableItem] = field(default_factory=list)  # 预算外
    scores: dict[str, float] = field(default_factory=dict)
    priorities: dict[str, str] = field(default_factory=dict)     # item_id → MUST/SHOULD/MAY
    over_budget: bool = False        # MUST 项已超总预算（信号，非静默丢）

    @property
    def item_ids(self) -> list[str]:
        return [it.item_id for it in self.items]

    def by_bucket(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for it in self.items:
            out.setdefault(it.bucket, []).append(it.item_id)
        return out


# TODO(M4, review §2.4): 分桶语义待与 §8.2 重对齐——
#   fact 应归 character 桶（经历子桶），streaming 桶应是「过去章」script 而非本章。
#   现状 M1 无 embedding，桶标签暂不影响结果，接真检索/子预算前修。
_BUCKET_BY_MEMTYPE = {
    "fact": "trajectory",
    "belief": "character",
    "trait": "character",
    "voice": "character",
    "ability": "character",
    "goal": "character",
}


def _mem_to_item(m, as_of_chapter: int) -> RetrievableItem:
    return RetrievableItem(
        item_id=m.id,
        text=m.text,
        kind=f"memory:{m.type}",
        scope=m.scope,
        t_valid=m.t_valid,
        salience=m.salience,
        tier=int(m.tier),
        is_goal=(m.type == "goal"),
        bucket="streaming" if m.t_valid == as_of_chapter else _BUCKET_BY_MEMTYPE.get(m.type, "trajectory"),
    )


def retrieve(query: Query, mem_store, arc_store=None) -> RetrievalResult:
    # ── ① 过滤 ────────────────────────────────────────────
    candidates: list[RetrievableItem] = []
    for m in mem_store.as_of(query.as_of_chapter):
        if query.char is not None:
            if m.scope not in (query.char, "global"):
                continue
        candidates.append(_mem_to_item(m, query.as_of_chapter))

    if arc_store is not None:
        for a in arc_store.all():
            if a.established_ch > query.as_of_chapter:
                continue
            # 认知边界：as-of 本章不知情的 secret 不检回（knowledge[] 隐式补集）
            if a.kind == "secret" and query.char and not a.knows_as_of(query.char, query.as_of_chapter):
                continue
            candidates.append(
                RetrievableItem(
                    item_id=a.id, text=a.desc, kind=f"arc:{a.kind}",
                    scope="arc", t_valid=a.established_ch, salience=0.6, tier=None,
                    bucket="trajectory",
                )
            )

    if not candidates:
        return RetrievalResult()

    # ── ② 排序（确定性打分）──────────────────────────────
    focus_tokens = _tokenize(query.focus)
    bm25_scores = _bm25(candidates, focus_tokens)
    scored: list[tuple[float, RetrievableItem]] = []
    for it, focus_score in zip(candidates, bm25_scores):
        recency = 1.0 / (1.0 + max(0, query.as_of_chapter - it.t_valid))
        tier_w = 0.0 if it.tier is None else (3 - it.tier) / 3.0
        score = (
            W_SALIENCE * it.salience
            + W_RECENCY * recency
            + W_FOCUS * focus_score
            + W_TIER * tier_w
            + (GOAL_BOOST if it.is_goal else 0.0)
        )
        scored.append((score, it))
    # 稳定排序：分数降序，同分按 item_id 保证确定性
    scored.sort(key=lambda x: (-x[0], x[1].item_id))

    # ── ③ 分级 + 分桶预算 ─────────────────────────────────
    budget = query.budget_tokens
    weights = query.bucket_weights or DEFAULT_BUCKET_WEIGHTS
    tiers = {it.item_id: default_priority(it) for _, it in scored}
    cost_of = {it.item_id: count_tokens(it.text) for _, it in scored}

    result = RetrievalResult(
        scores={it.item_id: round(s, 4) for s, it in scored},
        priorities=tiers,
    )
    included: set[str] = set()
    used = 0

    # (a) MUST：必进，即便超预算（置信号）
    for _, it in scored:
        if tiers[it.item_id] != "MUST":
            continue
        result.items.append(it)
        included.add(it.item_id)
        used += cost_of[it.item_id]
    if used > budget:
        result.over_budget = True

    # (b) SHOULD：分桶子预算公平分配（基于 MUST 后的余量）
    remaining = max(0, budget - used)
    sub_budget = {b: w * remaining for b, w in weights.items()}
    bucket_used: dict[str, int] = defaultdict(int)
    for _, it in scored:
        if it.item_id in included or tiers[it.item_id] != "SHOULD":
            continue
        cost = cost_of[it.item_id]
        cap = sub_budget.get(it.bucket, 0.0)
        if used + cost <= budget and bucket_used[it.bucket] + cost <= cap:
            result.items.append(it)
            included.add(it.item_id)
            bucket_used[it.bucket] += cost
            used += cost

    # (c) 全局余量兜底：剩余 SHOULD + MAY 按分填，不浪费预算
    for _, it in scored:
        if it.item_id in included:
            continue
        cost = cost_of[it.item_id]
        if used + cost <= budget:
            result.items.append(it)
            included.add(it.item_id)
            used += cost

    result.dropped = [it for _, it in scored if it.item_id not in included]
    return result


def _bm25(candidates: list[RetrievableItem], focus_tokens: list[str]) -> list[float]:
    """归一化 BM25 词法相关分（无 focus 或语料退化时返回全 0）。"""
    if not focus_tokens:
        return [0.0] * len(candidates)
    corpus = [_tokenize(c.text) for c in candidates]
    if all(len(doc) == 0 for doc in corpus):
        return [0.0] * len(candidates)
    bm25 = BM25Okapi(corpus)
    raw = bm25.get_scores(focus_tokens)
    hi = max(raw) if len(raw) else 0.0
    if hi <= 0:
        return [0.0] * len(candidates)
    return [r / hi for r in raw]
