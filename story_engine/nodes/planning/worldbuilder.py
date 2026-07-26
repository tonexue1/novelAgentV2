"""Worldbuilder（世界构建）—— 对应 docs/nodes/planning/worldbuilder.md。

小核心大长尾：只种 L1 点名的承重 canon（core/major，带权威 definition），
海量 minor 由生产层现场造、Recorder 章末登记。

两个实现：`Worldbuilder`（真 LLM，M2）/ `WorldbuilderStub`（确定性，供 Gate UT）。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.primitives.enums import WorldTier
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.plan import L0, L1
from story_engine.schemas.stores.world import WorldEntity

_ROLE = "你是世界构建师，负责给全书种下**承重设定**（世界圣经的 core 条目）。"
_TASK = """为 L1 点名的每一个 world_refs 实体，写出权威定义。

硬要求（json 输出）：
- 每个 world_refs 里的 id **都要有**一条对应实体，entity_id 原样照抄，不得改写或漏项。
- definition 是这个概念在本书里的唯一权威解释（LLM 后续只读不重编），2~4 句，写实不写虚。
- tier 一律 core（这些是承重 canon）。
- canonical_name 用中文正名；aliases 填别称/旧称，没有就空数组。"""


class WorldbuilderOutput(SchemaModel):
    entities: list[WorldEntity] = Field(default_factory=list)


class Worldbuilder:
    name = "worldbuilder"

    def build_for(self, ctx: NodeContext, l1: L1, l0: L0 | None = None) -> list[WorldEntity]:
        if ctx.llm is None:
            raise ValueError("Worldbuilder 需要 LLMClient；无 LLM 场景请用 WorldbuilderStub")
        if not l1.world_refs:
            return []
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("立意 L0", as_json(l0) if l0 else ""),
                ("待定义的承重 canon（world_refs）", as_json(l1.world_refs)),
                ("全书结构 L1（供理解这些 canon 怎么被用）", as_json(l1, limit=2000)),
            ],
        )
        out = ctx.llm.complete_structured(prompt, WorldbuilderOutput, node=self.name, chapter=0)
        return self._normalize(out.entities, l1)

    def _normalize(self, entities: list[WorldEntity], l1: L1) -> list[WorldEntity]:
        """只保留 L1 点名的 id 并去重——多余的实体属于长尾，创世不种。"""
        wanted = list(dict.fromkeys(l1.world_refs))
        by_id = {e.entity_id: e for e in entities if e.entity_id in set(wanted)}
        for e in by_id.values():
            e.tier = WorldTier.CORE
        return [by_id[r] for r in wanted if r in by_id]


class WorldbuilderStub:
    """给每个 world_ref 造一个带 definition 的 core 实体，令 Gate 闭包通过。"""

    name = "worldbuilder"

    def build_for(self, l1: L1) -> list[WorldEntity]:
        return [
            WorldEntity(
                entity_id=ref,
                canonical_name=ref.split(".", 1)[-1],
                tier=WorldTier.CORE,
                definition=f"{ref} 的权威定义（M0 stub）",
            )
            for ref in l1.world_refs
        ]
