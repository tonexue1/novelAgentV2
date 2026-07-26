"""创世子流程 —— 对应 ARCHITECTURE §2.6（G0-G5）。

控制流：G0 摄入 → G1 立意 → G2 协同循环⇄Gate → G3 收口 → G4 L2[卷1] → G5 台账+画像。
给了 ctx.llm 就走真 LLM 节点（M2），否则回落 stub（确定性 UT）。
人工共创触点（G1/G2/G3）M2 自动放行——是暂缓不是取消，交互口子 M3+ 补。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.planning.architect import Architect, ArchitectStub
from story_engine.nodes.planning.worldbuilder import Worldbuilder, WorldbuilderStub
from story_engine.nodes.system.applier import ApplierStub
from story_engine.nodes.validation.genesis_gate import check_closure
from story_engine.schemas.artifacts.genesis_gap import GenesisGap, GenesisVerdict
from story_engine.schemas.artifacts.seed import Seed
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L0, L1, L2
from story_engine.schemas.stores.world import WorldEntity


@dataclass
class GenesisResult:
    """S₀：创世产物（清单见 ARCHITECTURE §2.6）。"""

    l0: L0
    l1: L1
    world: list[WorldEntity]
    arcs: list[ArcRecord]
    gap: GenesisGap
    l2: L2 | None = None                                   # G4 首卷大纲
    profiles: list[MemoryEntry] = field(default_factory=list)  # G5 tier0/1 seed 画像
    iterations: int = 0
    trace: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.gap.verdict == GenesisVerdict.PASS


def run_genesis(
    seed: Seed,
    *,
    max_iter: int = 3,
    ctx: NodeContext | None = None,
) -> GenesisResult:
    """seed → S₀。G2 协同循环最多 max_iter 轮，Gate 判收敛。

    ctx 带 llm → 真 LLM 创世；否则确定性 stub。
    """
    use_llm = ctx is not None and ctx.llm is not None
    applier = ApplierStub()
    architect = Architect() if use_llm else ArchitectStub()
    trace: list[str] = ["G0 种子摄入"]

    # G1 立意 + L1 骨架
    if use_llm:
        l0, l1 = architect.bootstrap(ctx, seed)
    else:
        l0, l1 = architect.bootstrap(seed)
    trace.append("G1 L0 立意 + L1 骨架")

    # G2 协同循环 ⇄ Gate
    world: list[WorldEntity] = []
    gap = GenesisGap(verdict=GenesisVerdict.REITERATE)
    for i in range(max_iter):
        if use_llm:
            world = Worldbuilder().build_for(ctx, l1, l0)
        else:
            world = WorldbuilderStub().build_for(l1)
        gap = check_closure(l0, l1, world, iteration=i, max_iter=max_iter - 1)
        trace.append(f"G2 迭代{i}: Gate={gap.verdict.value}")
        if gap.verdict != GenesisVerdict.REITERATE:
            break

    # G3~G5 仅在收敛时（未收敛的创世包没资格铺开首卷）
    l2: L2 | None = None
    profiles: list[MemoryEntry] = []
    arcs: list[ArcRecord] = []
    if gap.verdict == GenesisVerdict.PASS:
        trace.append("G3 整包收口（M2 自动放行，人工关卡暂缓）")
        if use_llm:
            l2 = architect.expand_volume(ctx, l0, l1)
            profiles = architect.seed_profiles(ctx, seed, l0, l1)
        else:
            l2 = architect.expand_volume(l1)
            profiles = architect.seed_profiles(seed, l1)
        trace.append("G4 L2[卷1] 首卷铺开")
        arcs = applier.init_arcs(l1)
        trace.append("G5 ArcStore 台账 + seed 画像初始化")

    return GenesisResult(
        l0=l0, l1=l1, world=world, arcs=arcs, gap=gap,
        l2=l2, profiles=profiles,
        iterations=len(trace), trace=trace,
    )
