"""ConsistencyGate：阶梯决策面（假 Critic / 硬检，不打真网）。"""

from story_engine.nodes.base import NodeContext
from story_engine.nodes.system.consistency_gate import ConsistencyGate
from story_engine.nodes.system.violation_log import ViolationTracker
from story_engine.primitives.enums import Severity
from story_engine.primitives.ids import mint_violation_id
from story_engine.schemas.artifacts.scene_script import ContractCast, Obligation, SceneContract
from story_engine.schemas.stores.script import SceneCast
from story_engine.schemas.stores.violation import Locus, Violation
from tests.factories import make_beat, make_scene


def _contract(**kw) -> SceneContract:
    base = dict(
        scene_id="c1.s1",
        location="loc.qing_yun",
        pov="char.ye_fan",
        goal="入门",
        conflict="门规",
        cast=[ContractCast(char="char.ye_fan", entry_state="紧张")],
        obligations=[Obligation(obligation_id="c1.s1.o1", desc="表明来意")],
    )
    base.update(kw)
    return SceneContract(**base)


def _clean_scene():
    scene = make_scene(
        "c1.s1",
        [make_beat("c1.s1.b1", hits="c1.s1.o1")],
        location="loc.qing_yun",
        pov="char.ye_fan",
    )
    scene.cast = [SceneCast(char="char.ye_fan", entry_state="紧张")]
    return scene


def _vio(
    *,
    severity: Severity,
    category: str = "logic",
    message: str = "问题",
    refs: list[str] | None = None,
) -> Violation:
    return Violation(
        id=mint_violation_id(),
        chapter=1,
        stage="character",
        check_type="llm",
        severity=severity,
        category=category,  # type: ignore[arg-type]
        locus=Locus(chapter="c1", scene="c1.s1"),
        refs=refs or [],
        message=message,
        escalation_level="scene",
    )


class _FakeCritic:
    def __init__(self, batch: list[Violation]) -> None:
        self.batch = batch

    def review(self, ctx, **_kw) -> list[Violation]:
        return list(self.batch)


def test_correct_exhausted_admits_flagged():
    gate = ConsistencyGate(ViolationTracker(), retry_budget=1)
    critic = _FakeCritic([_vio(severity=Severity.CORRECT, message="动机弱")])
    ctx = NodeContext()
    scene = _clean_scene()
    contract = _contract()

    d1 = gate.scene_gate(ctx, scene=scene, contract=contract, chapter=1, critic=critic)
    assert d1.action == "retry_scene"

    d2 = gate.scene_gate(ctx, scene=scene, contract=contract, chapter=1, critic=critic)
    assert d2.action == "admit"
    assert d2.flagged
    assert all(v.resolution == "flagged" for v in d2.violations)


def test_block_ladder_ends_in_block_action():
    gate = ConsistencyGate(ViolationTracker(), retry_budget=1, replan_budget=1)
    critic = _FakeCritic([
        _vio(
            severity=Severity.BLOCK,
            category="canon_contradiction",
            message="死人说话",
            refs=["m.dead"],
        )
    ])
    ctx = NodeContext()
    scene = _clean_scene()
    contract = _contract()

    assert gate.scene_gate(ctx, scene=scene, contract=contract, chapter=1, critic=critic).action == (
        "redirect_scene"
    )
    assert gate.scene_gate(ctx, scene=scene, contract=contract, chapter=1, critic=critic).action == (
        "replan_chapter"
    )
    d3 = gate.scene_gate(ctx, scene=scene, contract=contract, chapter=1, critic=critic)
    assert d3.action == "escalate_volume"
    assert all(v.resolution == "blocked" for v in d3.violations)


def test_beat_correct_retries_then_flagged():
    gate = ConsistencyGate(ViolationTracker(), retry_budget=1)
    beat = make_beat("c1.s1.b1", hits="c1.s1.o9")  # 幽灵承重拍 → CORRECT
    contract = _contract()

    d1 = gate.beat_gate(beat=beat, contract=contract, chapter=1)
    assert d1.action == "retry_beat"

    d2 = gate.beat_gate(beat=beat, contract=contract, chapter=1)
    assert d2.action == "admit"
    assert d2.flagged


def test_beat_block_exhausted_redirects_scene():
    gate = ConsistencyGate(ViolationTracker(), retry_budget=1)
    beat = make_beat("c1.s1.b1", owner="char.ghost")  # 不在 cast → BLOCK
    contract = _contract()

    assert gate.beat_gate(beat=beat, contract=contract, chapter=1).action == "retry_beat"
    d2 = gate.beat_gate(beat=beat, contract=contract, chapter=1)
    assert d2.action == "redirect_scene"


def test_advisory_only_admits_advised():
    gate = ConsistencyGate(ViolationTracker())
    # 承重拍未命中 → ADVISORY/logic；cast+地点齐，无 CORRECT/BLOCK
    scene = make_scene("c1.s1", [make_beat("c1.s1.b1")], pov="char.ye_fan")
    scene.cast = [SceneCast(char="char.ye_fan", entry_state="紧张")]
    d = gate.scene_gate(
        NodeContext(),
        scene=scene,
        contract=_contract(),
        chapter=1,
        world_ids={"loc.qing_yun"},
        critic=_FakeCritic([]),
    )
    assert d.action == "admit"
    assert not d.flagged
    assert d.violations
    assert all(v.resolution == "advised" for v in d.violations)
