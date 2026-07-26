"""Reconciler（对账）—— 对应 docs/nodes/recorder/reconciler.md。

把过校验的候选与相关旧记忆对账，决定写回动作：
  ADD / REINFORCE / SOFT-INVALIDATE / NOOP（**没有 DELETE，矛盾走软失效**）。

三条要害（冻结文档不变式 4/5/6）：
  - REINFORCE / SOFT-INVALIDATE 必须带真实存在的 target_id；
  - NOOP 留档供审计与幂等重建，Applier 只记日志不碰库；
  - 去重键 (scope, type, 归一化 text)。

LLM 定语义、系统兜底：LLM 判完之后，`_sanitize` 会把指不到实体的
target_id 一律降级；`_sanitize_arcs` 处理幽灵弧线 id。
绝不把非法 op 放给 Applier（那边是 fail-fast 的）。
"""

from __future__ import annotations

import string
import unicodedata
from dataclasses import dataclass, field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.schemas.artifacts.recorder_output import ArcOp, MemOp, RecorderOutput
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry

_ROLE = "你是档案管理员，负责把新抽出的条目和旧档案对账，决定每条**怎么入库**。"
_TASK = """逐条决定写回动作：

- ADD：档案里没有的新事实。
- REINFORCE：旧档案已有同一件事，这次只是又一次印证 → 填旧条目的 target_id。
- SOFT-INVALIDATE：旧档案被本章推翻了（目标达成、信念改变、状态过期）→
  填旧条目的 target_id，并给 resolution：achieved（达成）/ abandoned（放弃）/
  superseded（被新的取代）。**永远不要删除**，只标失效。
- NOOP：和旧档案完全重复、没有新增信息。

硬要求：
- REINFORCE / SOFT-INVALIDATE **必须**填 target_id，且只能填"相关旧记忆"里真实出现过的 id。
- 语义相同只是措辞不同 → 算重复，不要 ADD 出第二条。
- 被推翻的旧条目要显式给一条 SOFT-INVALIDATE，别只 ADD 新的把矛盾留在库里。
- evidence 原样保留，不要改写。"""

_KIND_PREFIX = {"foreshadow": "fs", "secret": "sec", "thread": "th"}
# op ↔ kind 兼容表（与 Applier 状态机对齐）；不合规的一律降 NOOP
_OPS_BY_KIND = {
    "foreshadow": frozenset({"PLANT", "REINFORCE", "FULFILL", "ABANDON", "NOOP"}),
    "secret": frozenset({"PLANT", "REINFORCE", "FULFILL", "ABANDON", "REVEAL", "NOOP"}),
    "thread": frozenset({"ADVANCE", "CLIMAX", "RESOLVE", "DROP", "NOOP"}),
}


@dataclass
class ReconcileResult:
    output: RecorderOutput
    coerced: list[dict] = field(default_factory=list)   # 被系统降级的 op，供审计


class ReconcilerOutput(SchemaModel):
    mem_ops: list[MemOp] = []


class Reconciler:
    name = "reconciler"

    def reconcile(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        candidates: RecorderOutput,
        related: list[MemoryEntry] | None = None,
        arcs: list[ArcRecord] | None = None,
    ) -> ReconcileResult:
        related = related or []
        arcs = arcs or []
        known_arcs = {a.id for a in arcs}
        coerced: list[dict] = []

        # 第 1 章通常无旧档案可对：省一次调用，mem 全部按 ADD 走
        if not related or not candidates.mem_ops:
            mem_ops = list(candidates.mem_ops)
        else:
            if ctx.llm is None:
                raise ValueError("Reconciler 需要 LLMClient")
            prompt = build_prompt(
                _ROLE,
                _TASK,
                [
                    ("本章新抽出的候选条目", as_json(candidates.mem_ops, limit=4000)),
                    ("相关旧记忆（可作 target_id 的全部候选）", as_json(_brief(related), limit=4000)),
                    ("本章章号", f"第 {chapter} 章"),
                ],
            )
            decided = ctx.llm.complete_structured(
                prompt, ReconcilerOutput, node=self.name, chapter=chapter, temperature=0
            )
            mem_ops, mem_coerced = self._sanitize(decided.mem_ops, related)
            coerced.extend(mem_coerced)
            mem_ops = self._dedupe(mem_ops, related, coerced)

        known_kinds = {a.id: a.kind for a in arcs}
        arc_ops, arc_coerced = self._sanitize_arcs(
            candidates.arc_ops, known_arcs, known_kinds
        )
        coerced.extend(arc_coerced)
        return ReconcileResult(
            output=RecorderOutput(
                chapter=candidates.chapter,
                mem_ops=mem_ops,
                arc_ops=arc_ops,
                world_ops=candidates.world_ops,
                tier_noms=candidates.tier_noms,
                extractor_version=candidates.extractor_version,
            ),
            coerced=coerced,
        )

    # ── 系统兜底 ────────────────────────────────────────────────
    def _sanitize(
        self, ops: list[MemOp], related: list[MemoryEntry]
    ) -> tuple[list[MemOp], list[dict]]:
        """target_id 指不到实体的 op 一律降级，绝不放给 fail-fast 的 Applier。"""
        known = {m.id for m in related}
        out: list[MemOp] = []
        coerced: list[dict] = []
        for op in ops:
            if op.action in {"REINFORCE", "SOFT-INVALIDATE"} and op.target_id not in known:
                reason = "target_id 缺失" if not op.target_id else f"target_id 不存在: {op.target_id}"
                if op.action == "REINFORCE" and op.text and op.type and op.scope:
                    coerced.append({"from": op.action, "to": "ADD", "reason": reason})
                    op = op.model_copy(update={"action": "ADD", "target_id": None})
                else:
                    coerced.append({"from": op.action, "to": "NOOP", "reason": reason})
                    op = op.model_copy(update={"action": "NOOP"})
            out.append(op)
        return out, coerced

    def _sanitize_arcs(
        self,
        ops: list[ArcOp],
        known_ids: set[str],
        known_kinds: dict[str, str] | None = None,
    ) -> tuple[list[ArcOp], list[dict]]:
        """幽灵 id / 错配 op：补前缀、升涌现、按 kind 拦非法转移，绝不放给 Applier。"""
        known_kinds = dict(known_kinds or {})
        out: list[ArcOp] = []
        coerced: list[dict] = []
        for op in ops:
            if op.op == "NOOP":
                out.append(op)
                continue
            tid = _norm_arc_id(op.target_id, op.kind)
            updates: dict = {}
            if tid != op.target_id:
                updates["target_id"] = tid
                coerced.append({
                    "from": "arc.target_id",
                    "to": tid,
                    "reason": f"补齐前缀: {op.target_id}",
                })
            if tid not in known_ids and not op.is_new:
                draft = op.draft or {"desc": tid}
                updates.update({"is_new": True, "draft": draft})
                coerced.append({
                    "from": "arc",
                    "to": "is_new",
                    "reason": f"弧线不存在，升为涌现提名: {tid}",
                })
            elif tid not in known_ids and op.is_new and not op.draft:
                updates["draft"] = {"desc": tid}
                coerced.append({
                    "from": "arc.draft",
                    "to": "default",
                    "reason": f"is_new 缺 draft，补默认: {tid}",
                })
            kind = known_kinds.get(tid) or updates.get("kind") or op.kind
            if tid not in known_ids:
                # 涌现：以 op.kind 为准（或 draft），记进本批 kind 表
                kind = op.kind
                known_kinds[tid] = kind
                known_ids = known_ids | {tid}
            allowed = _OPS_BY_KIND.get(kind, frozenset({"NOOP"}))
            final_op = op.op
            if final_op not in allowed:
                coerced.append({
                    "from": final_op,
                    "to": "NOOP",
                    "reason": f"op {final_op} 不适用于 {kind}（{tid}）",
                })
                updates["op"] = "NOOP"
            out.append(op.model_copy(update=updates) if updates else op)
        return out, coerced

    def _dedupe(
        self, ops: list[MemOp], related: list[MemoryEntry], coerced: list[dict]
    ) -> list[MemOp]:
        """按 (scope, type, 归一化 text) 去重：库里已有 → 转 NOOP；批内重复 → 丢弃。"""
        existing = {_key(m.scope, m.type, m.text) for m in related}
        seen: set[tuple[str, str, str]] = set()
        out: list[MemOp] = []
        for op in ops:
            if op.action != "ADD" or not (op.scope and op.type and op.text):
                out.append(op)
                continue
            key = _key(op.scope, op.type, op.text)
            if key in existing:
                coerced.append({"from": "ADD", "to": "NOOP", "reason": "与旧档案重复"})
                out.append(op.model_copy(update={"action": "NOOP"}))
                continue
            if key in seen:
                coerced.append({"from": "ADD", "to": "(丢弃)", "reason": "同批重复"})
                continue
            seen.add(key)
            out.append(op)
        return out


def _norm_arc_id(target_id: str, kind: str) -> str:
    prefix = _KIND_PREFIX.get(kind, "fs")
    if "." in target_id:
        return target_id
    return f"{prefix}.{target_id}"


_CJK_PUNCT = "，。、！？；：“”‘’（）《》〈〉【】…—·"
_STRIP = set(string.punctuation) | set(string.whitespace) | set(_CJK_PUNCT)


def _normalize(text: str) -> str:
    """归一化：全半角统一 + 去标点空白——措辞微调不该变成两条记录。"""
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in normalized if ch not in _STRIP).lower()


def _key(scope: str, mem_type: str, text: str) -> tuple[str, str, str]:
    return (scope, mem_type, _normalize(text))


def _brief(entries: list[MemoryEntry]) -> list[dict]:
    return [
        {
            "id": m.id,
            "type": m.type,
            "scope": m.scope,
            "text": m.text,
            "t_valid": m.t_valid,
            "strength": m.strength,
        }
        for m in entries
    ]
