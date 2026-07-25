"""WorldStore：WorldEntity —— 对应 docs/schema/stores/world-store.md。

M0 落地范围：Gate 闭包检查需要的 id/tier/definition。完整字段以文档为准。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.primitives.enums import WorldTier
from story_engine.schemas.base import SchemaModel


class WorldEntity(SchemaModel):
    """canon 实体（概念/功法/地理/势力/物件/种族）。"""

    entity_id: str  # concept.{slug} | art.{slug} | loc.{slug} | org.{slug} | item.{slug} | race.{slug}
    canonical_name: str
    tier: WorldTier = WorldTier.MINOR
    definition: str | None = None       # core/major 必须有权威定义
    aliases: list[str] = Field(default_factory=list)
    relations: list[str] = Field(default_factory=list)
    since_ch: int = 0                   # as-of 起点
