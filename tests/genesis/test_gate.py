"""Genesis Gate 确定性 UT —— 落实 EVALUATION §2.3 的创世 fixture。

对应 ARCHITECTURE §2.6 三条硬判：引用闭包 / 无悬挂 / 覆盖。
"""

from story_engine.nodes.validation.genesis_gate import check_closure
from story_engine.schemas.artifacts.genesis_gap import GenesisVerdict
from story_engine.schemas.stores.plan import L0, L1, Thread
from story_engine.schemas.stores.world import WorldEntity


def _l0() -> L0:
    return L0(
        logline="荒古后裔踏上成仙路",
        core_dramatic_question="仙是否真存在",
        ending_intent="揭穿成仙真相",
    )


def _l1(world_refs) -> L1:
    return L1(
        threads=[Thread(thread_id="th.xianlu", tier="main", desc="仙路")],
        world_refs=list(world_refs),
    )


def test_dangling_reference_caught():
    """L1 点名 world:北斗古星 但 WorldStore 没建 → 悬挂，REITERATE。"""
    l1 = _l1(["concept.jingjie", "loc.beidou"])
    world = [WorldEntity(entity_id="concept.jingjie", canonical_name="境界体系",
                         tier="core", definition="轮海→道宫→…")]
    gap = check_closure(_l0(), l1, world, iteration=0, max_iter=3)
    assert gap.dangling == ["loc.beidou"]
    assert gap.closure_ok is False
    assert gap.coverage_ok is True
    assert gap.verdict == GenesisVerdict.REITERATE


def test_missing_definition_caught():
    """core 实体存在但无权威 definition → missing_def。"""
    l1 = _l1(["concept.jingjie"])
    world = [WorldEntity(entity_id="concept.jingjie", canonical_name="境界体系",
                         tier="core", definition="")]
    gap = check_closure(_l0(), l1, world)
    assert gap.missing_def == ["concept.jingjie"]
    assert gap.closure_ok is False


def test_coverage_fail_without_main_thread():
    l0 = _l0()
    l1 = L1(threads=[Thread(thread_id="th.side", tier="local", desc="支线")], world_refs=[])
    gap = check_closure(l0, l1, [])
    assert gap.coverage_ok is False
    assert gap.uncovered


def test_pass_when_closed_and_covered():
    l1 = _l1(["concept.jingjie"])
    world = [WorldEntity(entity_id="concept.jingjie", canonical_name="境界体系",
                         tier="core", definition="轮海→道宫→…")]
    gap = check_closure(_l0(), l1, world)
    assert gap.verdict == GenesisVerdict.PASS
    assert gap.closure_ok and gap.coverage_ok


def test_escalate_at_max_iter():
    l1 = _l1(["loc.missing"])
    gap = check_closure(_l0(), l1, [], iteration=3, max_iter=3)
    assert gap.verdict == GenesisVerdict.ESCALATE
