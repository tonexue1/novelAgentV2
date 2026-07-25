"""Genesis Gate —— 创世收敛判据（确定性硬检部分）。

对应 ARCHITECTURE §2.6「G2 收敛判据」。这是系统里第一个天然确定性、
不需要 LLM、自包含的检查——纯图/集合运算，最适合做成确定性 UT。

三条硬判：
  ① 引用闭包：L1.world_refs 的每个 id 在 WorldStore 存在，且 core/major 有权威 definition。
  ② 无悬挂：L1 要但 WorldStore 没建的 world id（= dangling）。
  ③ 覆盖：L0 的核心问题 / ending 至少被 1 条 main thread 支撑。
软复核（完备性）走 LLM，不在本函数。
"""

from __future__ import annotations

from story_engine.primitives.enums import WorldTier
from story_engine.schemas.artifacts.genesis_gap import GenesisGap, GenesisVerdict
from story_engine.schemas.stores.plan import L0, L1
from story_engine.schemas.stores.world import WorldEntity


def check_closure(
    l0: L0,
    l1: L1,
    world: list[WorldEntity],
    *,
    iteration: int = 0,
    max_iter: int = 3,
) -> GenesisGap:
    """纯函数：给定 L0 + L1 + WorldStore 快照，返回 GenesisGap 诊断。"""
    by_id: dict[str, WorldEntity] = {w.entity_id: w for w in world}

    dangling: list[str] = []
    missing_def: list[str] = []
    for ref in l1.world_refs:
        ent = by_id.get(ref)
        if ent is None:
            dangling.append(ref)          # 悬挂：引用了不存在的实体
            continue
        if ent.tier in (WorldTier.CORE, WorldTier.MAJOR) and not (ent.definition or "").strip():
            missing_def.append(ref)       # 承重 canon 缺权威定义

    # 覆盖：核心问题需至少一条 main thread 撑
    has_main = any(t.tier == "main" for t in l1.threads)
    uncovered: list[str] = []
    if l0.core_dramatic_question and not has_main:
        uncovered.append("core_dramatic_question 无 main thread 支撑")
    if l0.ending_intent and not has_main:
        uncovered.append("ending_intent 无 main thread 支撑")

    closure_ok = not dangling and not missing_def
    coverage_ok = not uncovered

    if closure_ok and coverage_ok:
        verdict = GenesisVerdict.PASS
    elif iteration >= max_iter:
        verdict = GenesisVerdict.ESCALATE
    else:
        verdict = GenesisVerdict.REITERATE

    return GenesisGap(
        verdict=verdict,
        iteration=iteration,
        dangling=dangling,
        missing_def=missing_def,
        uncovered=uncovered,
    )
