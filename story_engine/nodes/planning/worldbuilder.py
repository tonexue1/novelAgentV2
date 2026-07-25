"""Worldbuilder（世界构建）—— M0 stub。

真实职责：据 L1 点名，补 core/major canon 的权威 definition。见 docs/nodes/planning/worldbuilder.md。
M0 stub：给 L1.world_refs 的每个 id 造一个带 definition 的 core 实体，令 Gate 闭包通过。
"""

from __future__ import annotations

from story_engine.schemas.stores.plan import L1
from story_engine.schemas.stores.world import WorldEntity


class WorldbuilderStub:
    name = "worldbuilder"

    def build_for(self, l1: L1) -> list[WorldEntity]:
        out: list[WorldEntity] = []
        for ref in l1.world_refs:
            out.append(
                WorldEntity(
                    entity_id=ref,
                    canonical_name=ref.split(".", 1)[-1],
                    tier="core",
                    definition=f"{ref} 的权威定义（M0 stub）",
                )
            )
        return out
