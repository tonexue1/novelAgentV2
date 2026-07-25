"""Architect（总纲师）—— M0 stub。

真实职责：seed → L0(冻结) + L1 + L2[卷1]（创世自上而下）。见 docs/nodes/planning/architect.md。
M0 stub：把 seed 确定性映射成最小 L0 + L1（一条 main thread + 若干 world_refs），
不打 LLM，只为把创世管道跑通。真实 LLM 逻辑留 M2。
"""

from __future__ import annotations

from story_engine.primitives.ids import mint_entity, mint_volume
from story_engine.schemas.stores.plan import (
    L0,
    L1,
    Foreshadow,
    Thread,
    Volume,
)


class ArchitectStub:
    name = "architect"

    def bootstrap(self, seed) -> tuple[L0, L1]:  # noqa: ANN001 - Seed
        l0 = L0(
            logline=seed.logline,
            genre=list(seed.genre),
            tone=list(seed.tone),
            core_dramatic_question=f"围绕『{seed.logline}』的核心命题",
            ending_intent=seed.ending_intent,
            protagonist_arc_intent=list(seed.protagonist_intent),
        )
        main_thread = Thread(
            thread_id=mint_entity("th", "main"),
            tier="main",
            desc=seed.logline,
        )
        l1 = L1(
            version=1,
            created_at_ch=0,
            volumes=[Volume(vol_id=mint_volume(1), title="第一卷", detail_level="detailed")],
            threads=[main_thread],
            foreshadow_map=[
                Foreshadow(fs_id=mint_entity("fs", "core"), desc="核心伏笔占位")
            ],
            # 点名需要的承重 canon（stub：一个境界体系概念）
            world_refs=[mint_entity("concept", "power_system")],
        )
        return l0, l1
