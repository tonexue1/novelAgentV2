"""MemoryStore：MemoryEntry —— 对应 docs/schema/stores/memory-store.md。

派生投影：有损、evidence 回指、软失效。M0 最小落地。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import CharTier
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel

MemType = Literal["fact", "belief", "trait", "voice", "ability", "goal"]


class MemoryEntry(SchemaModel):
    mem_id: str                      # m.{ulid}
    scope: str                       # char:{slug} | world | ...
    type: MemType
    text: str
    tier: CharTier = CharTier.T3
    salience: float = 0.5
    t_valid: int = 0                 # as-of 生效章
    t_invalid: int | None = None     # 软失效章（None=仍有效）
    origin: str = "extracted"        # extracted | seeded
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    parent: str | None = None        # goal.parent 引用另一 mem_id
