"""创世子流程骨架 —— 对应 ARCHITECTURE §2.6（G0-G5）。

M0：把控制流打通（G0 摄入 → G1 立意 → G2 协同循环⇄Gate → G5 台账），
节点用 stub、Gate 用真实闭包检查。人工共创触点（G1/G2/G3）M0 先自动放行。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.nodes.planning.architect import ArchitectStub
from story_engine.nodes.planning.worldbuilder import WorldbuilderStub
from story_engine.nodes.system.applier import ApplierStub
from story_engine.nodes.validation.genesis_gate import check_closure
from story_engine.schemas.artifacts.genesis_gap import GenesisGap, GenesisVerdict
from story_engine.schemas.artifacts.seed import Seed
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.plan import L0, L1
from story_engine.schemas.stores.world import WorldEntity


@dataclass
class GenesisResult:
    """S₀：创世产物。"""

    l0: L0
    l1: L1
    world: list[WorldEntity]
    arcs: list[ArcRecord]
    gap: GenesisGap
    iterations: int = 0
    trace: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.gap.verdict == GenesisVerdict.PASS


def run_genesis(seed: Seed, *, max_iter: int = 3) -> GenesisResult:
    """seed → S₀。G2 协同循环最多 max_iter 轮，Gate 判收敛。"""
    architect = ArchitectStub()
    worldbuilder = WorldbuilderStub()
    applier = ApplierStub()
    trace: list[str] = ["G0 种子摄入"]

    # G1 立意 + L1 骨架
    l0, l1 = architect.bootstrap(seed)
    trace.append("G1 L0 立意 + L1 骨架")

    # G2 协同循环 ⇄ Gate
    world: list[WorldEntity] = []
    gap = GenesisGap(verdict=GenesisVerdict.REITERATE)
    for i in range(max_iter):
        world = worldbuilder.build_for(l1)          # 补 canon
        gap = check_closure(l0, l1, world, iteration=i, max_iter=max_iter - 1)
        trace.append(f"G2 迭代{i}: Gate={gap.verdict.value}")
        if gap.verdict != GenesisVerdict.REITERATE:
            break

    # G5 台账初始化（仅在收敛时）
    arcs: list[ArcRecord] = []
    if gap.verdict == GenesisVerdict.PASS:
        arcs = applier.init_arcs(l1)
        trace.append("G5 ArcStore 台账初始化")

    return GenesisResult(
        l0=l0, l1=l1, world=world, arcs=arcs, gap=gap,
        iterations=len(trace), trace=trace,
    )
