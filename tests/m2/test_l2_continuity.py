"""L2 事件链连续性硬检。"""

import pytest

from story_engine.nodes.planning.l2_continuity import (
    L2ContinuityError,
    assert_l2_continuity,
)
from story_engine.schemas.stores.plan import ChapterBeat, L2, VolumeSpine


def _spine() -> VolumeSpine:
    return VolumeSpine(
        shared_pressure="共享压力",
        inciting="发动",
        midpoint="中段",
        climax="收束",
    )


def _chain() -> list[ChapterBeat]:
    return [
        ChapterBeat(
            planned_seq=1,
            event="压力落地",
            leaves_open=["hook_a"],
            inherits=["spine.shared_pressure"],
            touches_spine="pressure",
            pov_focus=["char.a"],
        ),
        ChapterBeat(
            planned_seq=2,
            event="发动",
            leaves_open=["hook_b"],
            inherits=["hook_a"],
            touches_spine="inciting",
            pov_focus=["char.a"],
        ),
        ChapterBeat(
            planned_seq=3,
            event="质变",
            leaves_open=["hook_c"],
            inherits=["hook_b"],
            touches_spine="midpoint",
            pov_focus=["char.b"],
        ),
        ChapterBeat(
            planned_seq=4,
            event="收束",
            leaves_open=["hook_d"],
            inherits=["hook_c"],
            touches_spine="climax",
            pov_focus=["char.a", "char.b"],
        ),
    ]


def test_valid_event_chain_passes():
    assert_l2_continuity(L2(vol_id="v1", volume_spine=_spine(), chapter_beats=_chain()))


def test_ab_split_without_relay_fails():
    """A 章 / B 章 POV 不相交且未继承上一章钩子 → 打回。"""
    beats = [
        ChapterBeat(
            planned_seq=1,
            event="只写 A",
            leaves_open=["a_daily"],
            inherits=["spine.shared_pressure"],
            touches_spine="pressure",
            pov_focus=["char.a"],
        ),
        ChapterBeat(
            planned_seq=2,
            event="只写 B，不接 A",
            leaves_open=["b_daily"],
            inherits=["spine.shared_pressure"],  # 只挂脊骨，未接上一章
            touches_spine="inciting",
            pov_focus=["char.b"],
        ),
        ChapterBeat(
            planned_seq=3,
            event="汇合",
            leaves_open=["met"],
            inherits=["b_daily"],
            touches_spine="midpoint",
            pov_focus=["char.a", "char.b"],
        ),
        ChapterBeat(
            planned_seq=4,
            event="收",
            leaves_open=["end"],
            inherits=["met"],
            touches_spine="climax",
            pov_focus=["char.a", "char.b"],
        ),
    ]
    with pytest.raises(L2ContinuityError, match="POV 不相交"):
        assert_l2_continuity(L2(vol_id="v1", volume_spine=_spine(), chapter_beats=beats))


def test_missing_spine_touch_fails():
    beats = _chain()
    beats[3].touches_spine = "bridge"
    with pytest.raises(L2ContinuityError, match="climax"):
        assert_l2_continuity(L2(vol_id="v1", volume_spine=_spine(), chapter_beats=beats))


def test_broken_inherit_fails():
    beats = _chain()
    beats[1].inherits = ["never_planted"]
    with pytest.raises(L2ContinuityError, match="无法解析"):
        assert_l2_continuity(L2(vol_id="v1", volume_spine=_spine(), chapter_beats=beats))


def test_inciting_too_late_fails():
    beats = _chain()
    beats[1].touches_spine = "bridge"  # 挪走早段 inciting
    beats.append(
        ChapterBeat(
            planned_seq=5,
            event="过晚发动",
            leaves_open=["late"],
            inherits=["hook_d"],
            touches_spine="inciting",
            pov_focus=["char.a"],
        )
    )
    with pytest.raises(L2ContinuityError, match="inciting"):
        assert_l2_continuity(L2(vol_id="v1", volume_spine=_spine(), chapter_beats=beats))
