"""ArcStore：ArcRecord —— 对应 docs/schema/stores/arc-store.md。

伏笔 / 主线 / secret 三合一，靠 kind 判别，共享状态机。派生投影，evidence 回指。
字段严格对齐冻结文档（含 as-of knowledge[]、history[] 回溯、状态机块）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import Importance
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.plan import PayoffDeadline

ArcKind = Literal["foreshadow", "secret", "thread"]
ArcState = Literal["PLANNED", "PLANTED", "REINFORCED", "FULFILLED", "ABANDONED"]
ThreadState = Literal["OPEN", "ADVANCING", "CLIMAX", "RESOLVED", "DROPPED"]
ThreadTier = Literal["main", "saga", "local"]


class Knowledge(SchemaModel):
    """as-of 知情项。"第 N 章谁知道" = since_ch ≤ N 集合，hidden_from 为隐式补集。"""

    char: str                        # char.{slug}
    since_ch: int
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ArcTransition(SchemaModel):
    """history[] 元素：状态时间线，供 as-of 回溯。"""

    ch: int
    transition: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ThreadAdvance(SchemaModel):
    ch: int
    milestone: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class ArcRecord(SchemaModel):
    id: str                          # fs.{slug} | sec.{slug} | th.{slug}
    kind: ArcKind
    desc: str
    origin: Literal["planned", "emergent"] = "planned"
    established_ch: int = 0
    history: list[ArcTransition] = Field(default_factory=list)  # as-of 回溯
    extractor_version: str | None = None
    # —— 伏笔 / 秘密 共享状态机 ——
    importance: Importance | None = None
    state: ArcState | None = None
    payoff_deadline: PayoffDeadline | None = None
    plant_evidence: list[EvidenceSpan] = Field(default_factory=list)
    fulfill_evidence: list[EvidenceSpan] = Field(default_factory=list)
    abandon_reason: str | None = None      # ABANDONED 必填，绝不静默悬空
    linked_thread: str | None = None
    # —— secret 专属 ——
    knowledge: list[Knowledge] = Field(default_factory=list)  # as-of 知情名单
    # —— thread 专属 ——
    thread_state: ThreadState | None = None
    tier: ThreadTier | None = None
    advances: list[ThreadAdvance] = Field(default_factory=list)

    def knows_as_of(self, char: str, chapter: int) -> bool:
        """secret 认知边界：char 在第 chapter 章是否知情。"""
        return any(k.char == char and k.since_ch <= chapter for k in self.knowledge)

    @classmethod
    def llm_vocab(cls) -> str:
        return (
            "ArcRecord（入参台账行；写 ArcOp 前必看 state/thread_state）：\n"
            "- id: fs.|sec.|th.{slug}\n"
            "- kind: foreshadow | secret | thread\n"
            "- foreshadow/secret.state: PLANNED | PLANTED | REINFORCED | FULFILLED | ABANDONED\n"
            "- thread.thread_state: OPEN | ADVANCING | CLIMAX | RESOLVED | DROPPED\n"
            "- 对 PLANNED 只能 PLANT（或 NOOP），不能 REINFORCE/FULFILL。"
        )

    @classmethod
    def llm_input_brief(cls, arcs: list["ArcRecord"], *, limit: int = 60) -> str:
        """入参上下文：当前台账摘要 + 本 schema 取值说明。"""
        lines = [cls.llm_vocab(), "", "当前台账（id / kind / state）："]
        if not arcs:
            lines.append("（空）")
            return "\n".join(lines)
        for a in arcs[:limit]:
            st = a.state if a.kind != "thread" else a.thread_state
            lines.append(f"- {a.id} | {a.kind} | {st}")
        if len(arcs) > limit:
            lines.append(f"…另有 {len(arcs) - limit} 条未列出")
        return "\n".join(lines)
