"""ArcStore：ArcRecord —— 对应 docs/schema/stores/arc-store.md。

伏笔 / 主线 / secret 台账。派生投影，evidence 回指。M0 最小落地。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel

ArcKind = Literal["thread", "foreshadow", "secret"]
ArcStatus = Literal["OPEN", "PLANNED", "PLANTED", "REINFORCED", "FULFILLED", "ABANDONED"]


class ArcRecord(SchemaModel):
    arc_id: str                      # th.{slug} | fs.{slug} | sec.{slug}
    kind: ArcKind
    status: ArcStatus
    desc: str
    since_ch: int = 0
    known_by: list[str] = Field(default_factory=list)   # secret 用
    hidden_from: list[str] = Field(default_factory=list)
    evidence: list[EvidenceSpan] = Field(default_factory=list)
