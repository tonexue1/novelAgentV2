"""SummaryStore：SummaryEntry / SummaryDelta —— 对应 docs/schema/stores/summary-store.md。

Script 的多分辨率派生投影。独立于 RecorderOutput；Applier 章末/卷末幂等 upsert。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel

SummaryLevel = Literal["scene", "chapter", "volume", "saga"]
ProducedBy = Literal["Summarizer", "Replanner"]


class KeyOp(SchemaModel):
    op: str
    id: str


class SummaryEntry(SchemaModel):
    """多分辨率摘要；(level, ref) 为唯一键。"""

    level: SummaryLevel
    ref: str                             # c{n}.s{m} | c{n} | v{k} | sg{j}
    text: str
    vec: list[float] | None = None       # 建在 text 上；M4b Embedder 写入
    covers: list[EvidenceSpan] = Field(default_factory=list)
    threads: list[str] = Field(default_factory=list)
    cast: list[str] = Field(default_factory=list)
    key_ops: list[KeyOp] = Field(default_factory=list)
    t_valid: int = 0
    produced_by: ProducedBy = "Summarizer"
    summarizer_version: str = "v1"
    key: str = ""                        # JsonStore 主键 = f"{level}:{ref}"

    @model_validator(mode="after")
    def _set_key(self) -> "SummaryEntry":
        object.__setattr__(self, "key", f"{self.level}:{self.ref}")
        return self

    @property
    def store_key(self) -> str:
        return self.key or f"{self.level}:{self.ref}"


class SummaryDelta(SchemaModel):
    """Summarizer/Replanner → Applier，独立于 RecorderOutput。"""

    chapter: int
    entries: list[SummaryEntry] = Field(default_factory=list)
    produced_by: ProducedBy = "Summarizer"
