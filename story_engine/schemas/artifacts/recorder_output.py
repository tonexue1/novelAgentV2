"""RecorderOutput / MemOp / ArcOp —— 对应 docs/schema/artifacts/recorder-output.md。

Recorder（Extractor）抽取增量。**抽取是 LLM（M2），应用是确定性（M1 Applier）**。
字段严格对齐冻结文档（action 值集、target_id、strength/involves 等）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import Resolution
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.memory import GoalKind, MemType

MemAction = Literal["ADD", "REINFORCE", "SOFT-INVALIDATE", "NOOP"]
ArcOpName = Literal[
    "PLANT", "REINFORCE", "FULFILL", "ABANDON",   # fs/secret 状态机
    "REVEAL",                                       # secret 知情变更
    "ADVANCE", "CLIMAX", "RESOLVE", "DROP",         # thread 进度
    "NOOP",
]


class MemOp(SchemaModel):
    """对 MemoryStore 的一步操作，字段对齐 memory-store。"""

    action: MemAction
    target_id: str | None = None           # REINFORCE/SOFT-INVALIDATE 必填，指既有 m.{ulid}
    # —— 条目载荷（ADD 必填）——
    type: MemType | None = None
    scope: str | None = None               # char.{slug} | th.{slug} | global
    text: str | None = None
    strength: float | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    involves: list[str] = Field(default_factory=list)           # fact
    salience: float = 0.5                                       # fact
    goal_kind: GoalKind | None = None
    parent: str | None = None
    example: str | None = None
    resolution: Resolution | None = None   # 配 SOFT-INVALIDATE：achieved|abandoned|superseded


class ArcOp(SchemaModel):
    """对 ArcStore 台账的一步操作（状态机转移），字段对齐 arc-store。"""

    target_id: str                         # fs.{slug} | sec.{slug} | th.{slug}
    kind: Literal["foreshadow", "secret", "thread"] = "foreshadow"
    op: ArcOpName
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    abandon_reason: str | None = None      # ABANDON/DROP 必填
    reveal_to: list[str] = Field(default_factory=list)          # REVEAL：新增知情人
    milestone: str | None = None           # ADVANCE 描述
    is_new: bool = False                   # emergent 提名（新建 record）
    draft: dict | None = None              # 新建时草稿定义 {desc, kind, importance?, tier?}


class RecorderOutput(SchemaModel):
    """一章抽取的完整增量。world_ops / tier_noms 留 M2+。"""

    chapter: int
    mem_ops: list[MemOp] = Field(default_factory=list)
    arc_ops: list[ArcOp] = Field(default_factory=list)
    extractor_version: str | None = None
