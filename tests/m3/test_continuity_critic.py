"""Continuity Critic：严重度钳制（不靠模型自觉）。"""

from story_engine.nodes.validation.continuity_critic import (
    ContinuityCritic,
    CriticFinding,
)
from story_engine.primitives.enums import Severity
from tests.factories import make_beat, make_scene


def _scene():
    return make_scene("c2.s1", [make_beat("c2.s1.b1"), make_beat("c2.s1.b2")])


def test_block_logic_clamped_to_correct():
    v = ContinuityCritic()._to_violation(
        CriticFinding(
            severity="BLOCK",
            category="logic",
            beat_id="c2.s1.b1",
            message="少一拍铺垫",
            refs=["c2.s1.o1"],
        ),
        chapter=2,
        scene=_scene(),
    )
    assert v.severity == Severity.CORRECT
    assert v.category == "logic"


def test_block_voice_and_ooc_clamped():
    critic = ContinuityCritic()
    scene = _scene()
    for cat in ("voice", "OOC"):
        v = critic._to_violation(
            CriticFinding(severity="BLOCK", category=cat, message="偏了"),
            chapter=2,
            scene=scene,
        )
        assert v.severity == Severity.CORRECT, cat


def test_block_unknown_category_clamped():
    v = ContinuityCritic()._to_violation(
        CriticFinding(severity="BLOCK", category="weird", message="瞎报"),
        chapter=2,
        scene=_scene(),
    )
    assert v.category == "other"
    assert v.severity == Severity.CORRECT


def test_block_canon_without_refs_clamped():
    v = ContinuityCritic()._to_violation(
        CriticFinding(
            severity="BLOCK",
            category="canon_contradiction",
            message="他好像不该知道",
            refs=[],
        ),
        chapter=2,
        scene=_scene(),
    )
    assert v.severity == Severity.CORRECT


def test_block_canon_with_refs_kept():
    v = ContinuityCritic()._to_violation(
        CriticFinding(
            severity="BLOCK",
            category="canon_contradiction",
            message="推翻已入库事实",
            refs=["m.dead_already"],
        ),
        chapter=2,
        scene=_scene(),
    )
    assert v.severity == Severity.BLOCK
    assert v.refs == ["m.dead_already"]
