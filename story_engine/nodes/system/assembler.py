"""Assembler（上下文装配）—— 对应 docs/nodes/system/assembler.md。

按**节点画像**（读哪些桶、预算配额、分辨率）把 Retriever 的候选装配成该节点的上下文。

与 Retriever 的职责边界（别二次裁剪）：
  Retriever：filter → rank → budget（MUST/SHOULD/MAY 分级、分桶子预算、over_budget 信号）。
  Assembler：选画像、POV 认知边界过滤、把入选项渲染成 prompt 段。

M3 接三个节点：character（细，POV 过滤）/ continuity-critic（宽，独立检索）/ planner（粗）。
setup / dispatch / extractor 的画像留 M4。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.nodes.system.retriever import Query, RetrievableItem, retrieve

# 桶 → prompt 段标题（渲染用）
_BUCKET_LABEL = {
    "character": "人设与经历",
    "trajectory": "既有事实与线索",
    "streaming": "本章刚发生",
}


@dataclass(frozen=True)
class NodeProfile:
    """节点画像：这个节点该看多少、看哪些桶、要不要按 POV 收窄。"""

    node: str
    budget_tokens: int
    bucket_weights: dict[str, float]
    pov_scoped: bool = False       # 检索限定在单角色 scope + 认知边界内
    with_cognition: bool = False   # 附各角色认知边界清单（Critic 用）


PROFILES: dict[str, NodeProfile] = {
    # 细：只给这一个角色知道的东西，宁少勿多
    "character": NodeProfile(
        node="character",
        budget_tokens=1200,
        bucket_weights={"character": 0.6, "streaming": 0.3, "trajectory": 0.1},
        pov_scoped=True,
    ),
    # 宽：全局视角，独立做一次"这场戏可能推翻什么"的检索
    "continuity-critic": NodeProfile(
        node="continuity-critic",
        budget_tokens=3000,
        bucket_weights={"trajectory": 0.5, "character": 0.3, "streaming": 0.2},
        with_cognition=True,
    ),
    # 粗：长线为主，不要细节噪音
    "planner": NodeProfile(
        node="planner",
        budget_tokens=2000,
        bucket_weights={"trajectory": 0.7, "character": 0.2, "streaming": 0.1},
    ),
}


@dataclass
class AssembledContext:
    node: str
    items: list[RetrievableItem] = field(default_factory=list)
    dropped: list[RetrievableItem] = field(default_factory=list)
    over_budget: bool = False
    cognition: dict[str, list[str]] = field(default_factory=dict)  # char → 知情 secret id

    def facts(self) -> list[str]:
        """扁平文本行（Character 的 known_facts 等）。"""
        return [it.text for it in self.items]

    def sections(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for it in self.items:
            out.setdefault(_BUCKET_LABEL.get(it.bucket, it.bucket), []).append(it.text)
        return out

    def refs(self) -> list[str]:
        return [it.item_id for it in self.items]


class Assembler:
    name = "assembler"

    def assemble(
        self,
        *,
        node: str,
        chapter: int,
        mem_store,
        arc_store=None,
        char: str | None = None,
        focus: str = "",
        cast: list[str] | None = None,
        budget_tokens: int | None = None,
    ) -> AssembledContext:
        profile = PROFILES.get(node)
        if profile is None:
            raise ValueError(f"未知节点画像: {node!r}（已有 {sorted(PROFILES)}）")

        query = Query(
            as_of_chapter=chapter,
            char=char if profile.pov_scoped else None,
            focus=focus,
            budget_tokens=budget_tokens or profile.budget_tokens,
            bucket_weights=profile.bucket_weights,
        )
        result = retrieve(query, mem_store, arc_store)

        items = result.items
        dropped = list(result.dropped)
        if profile.pov_scoped and char:
            # 兜一道：即便 arc_store 没接，也不让不知情的 secret 漏进画像
            kept, cut = _pov_filter(items, char, chapter, arc_store)
            items, dropped = kept, dropped + cut

        ctx = AssembledContext(
            node=node,
            items=items,
            dropped=dropped,
            over_budget=result.over_budget,
        )
        if profile.with_cognition and arc_store is not None:
            ctx.cognition = _cognition_map(cast or [], chapter, arc_store)
        return ctx

    # ── 便捷口子（编排直接用）────────────────────────────────
    def known_facts(
        self, *, char: str, chapter: int, mem_store, arc_store=None, focus: str = ""
    ) -> list[str]:
        """Character 的认知边界内已知事实。非角色 owner（ENV/NARRATION）无画像。"""
        if char in {"ENV", "NARRATION"}:
            return []
        return self.assemble(
            node="character",
            chapter=chapter,
            mem_store=mem_store,
            arc_store=arc_store,
            char=char,
            focus=focus,
        ).facts()


def _pov_filter(
    items: list[RetrievableItem], char: str, chapter: int, arc_store
) -> tuple[list[RetrievableItem], list[RetrievableItem]]:
    kept: list[RetrievableItem] = []
    cut: list[RetrievableItem] = []
    for it in items:
        if it.kind == "arc:secret":
            arc = arc_store.get(it.item_id) if arc_store is not None else None
            if arc is None or not arc.knows_as_of(char, chapter):
                cut.append(it)
                continue
        if it.scope.startswith("char.") and it.scope != char:
            cut.append(it)  # 别人的内心戏不进你的画像
            continue
        kept.append(it)
    return kept, cut


def _cognition_map(cast: list[str], chapter: int, arc_store) -> dict[str, list[str]]:
    """各角色 as-of 知情的 secret 清单——Critic 判"他怎么会知道"的依据。"""
    secrets = [a for a in arc_store.all() if a.kind == "secret"]
    return {c: [s.id for s in secrets if s.knows_as_of(c, chapter)] for c in cast}
