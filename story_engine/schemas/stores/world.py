"""WorldStore：WorldEntity —— 对应 docs/schema/stores/world-store.md。

定义域慢变版本化 + 演化域 as-of 软失效。字段严格对齐冻结文档。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from story_engine.primitives.enums import WorldTier
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel, Temporal

WorldKind = Literal["concept", "art", "location", "faction", "item", "race"]
WorldOrigin = Literal["seeded", "emergent"]
WorldStatus = Literal["active", "retconned"]

_PREFIX_KIND: dict[str, WorldKind] = {
    "concept": "concept",
    "art": "art",
    "loc": "location",
    "org": "faction",
    "item": "item",
    "race": "race",
}


class WorldRelation(SchemaModel):
    type: str                            # 包含/相邻/从属/敌对/依赖…
    target_id: str


class WorldEntity(SchemaModel, Temporal):
    """canon 实体（概念/功法/地理/势力/物件/种族）。主键 id，对齐文档。"""

    id: str                              # concept.|art.|loc.|org.|item.|race.{slug}
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    kind: WorldKind | None = None
    tier: WorldTier = WorldTier.MINOR
    origin: WorldOrigin = "seeded"
    # —— 定义域 ——
    definition: str | None = None        # core/major 必须有权威定义
    attributes: dict[str, Any] = Field(default_factory=dict)
    relations: list[WorldRelation] = Field(default_factory=list)
    # —— 演化域 ——
    state: dict[str, Any] = Field(default_factory=dict)
    t_valid: int = 0
    t_invalid: int | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    # —— 元 ——
    version: int = 1
    status: WorldStatus = "active"
    established_ch: int = 0

    @model_validator(mode="before")
    @classmethod
    def _compat_entity_id(cls, data: Any) -> Any:
        """兼容旧构造参数 entity_id / since_ch / 扁平 relations。"""
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "id" not in d and "entity_id" in d:
            d["id"] = d.pop("entity_id")
        if "established_ch" not in d and "since_ch" in d:
            d["established_ch"] = d.pop("since_ch")
        if "t_valid" not in d and "established_ch" in d:
            d["t_valid"] = d["established_ch"]
        # 旧版 relations 是 list[str]，升为 typed
        rels = d.get("relations")
        if isinstance(rels, list) and rels and isinstance(rels[0], str):
            d["relations"] = [{"type": "related", "target_id": r} for r in rels]
        return d

    @model_validator(mode="after")
    def _infer_kind(self) -> "WorldEntity":
        if self.kind is None:
            prefix = self.id.split(".", 1)[0] if "." in self.id else ""
            object.__setattr__(self, "kind", _PREFIX_KIND.get(prefix, "concept"))
        return self

    # 兼容旧调用方（.entity_id）
    @property
    def entity_id(self) -> str:
        return self.id
