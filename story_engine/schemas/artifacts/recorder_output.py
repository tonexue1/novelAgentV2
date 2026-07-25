"""RecorderOutput / MemOp / ArcOp —— 对应 docs/schema/artifacts/recorder-output.md。

Recorder（Extractor）抽取增量。**抽取是 LLM（M2），应用是确定性（M1 Applier）**。
M1 手工造 RecorderOutput 喂 Applier 做确定性落库并配 UT。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.memory import MemType


class MemOp(SchemaModel):
    """对 MemoryStore 的一步操作。"""

    op: Literal["ADD", "INVALIDATE", "NOOP"]
    scope: str | None = None
    type: MemType | None = None
    text: str | None = None
    salience: float = 0.5
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    target_mem_id: str | None = None       # INVALIDATE 指向被失效的条目
    resolution: str | None = None          # achieved | abandoned | superseded
    parent: str | None = None              # goal 层级


class ArcOp(SchemaModel):
    """对 ArcStore 台账的一步操作（状态机转移）。"""

    op: Literal["OPEN", "PLANT", "REINFORCE", "FULFILL", "ABANDON", "NOOP"]
    arc_id: str
    kind: Literal["thread", "foreshadow", "secret"] = "foreshadow"
    desc: str | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    known_by: list[str] = Field(default_factory=list)
    hidden_from: list[str] = Field(default_factory=list)


class RecorderOutput(SchemaModel):
    """一章抽取的完整增量。"""

    chapter: int
    mem_ops: list[MemOp] = Field(default_factory=list)
    arc_ops: list[ArcOp] = Field(default_factory=list)
