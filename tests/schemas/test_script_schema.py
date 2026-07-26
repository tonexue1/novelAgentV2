"""ScriptStore 不变式 UT（对齐冻结 script-store.md）。

焊死的两条：type 与实现段必须一致；ENV/NARRATION 不得有台词。
"""

import pytest
from pydantic import ValidationError

from story_engine.schemas.stores.script import Action, Beat, Dialogue, Thought


def _beat(**kw) -> Beat:
    base = dict(beat_id="c1.s1.b1", owner="char.ye_fan", dramatic_goal="逼他摊牌")
    return Beat(**{**base, **kw})


def test_type_requires_matching_payload():
    with pytest.raises(ValidationError, match="必须填 dialogue 段"):
        _beat(type="dialogue")


def test_type_forbids_other_payload():
    with pytest.raises(ValidationError, match="不得同时填"):
        _beat(type="action", action=Action(stage="推门"), thought=Thought(inner="他在犹豫"))


def test_env_beat_cannot_speak():
    with pytest.raises(ValidationError, match="不得有台词"):
        _beat(owner="ENV", type="dialogue", dialogue=Dialogue(line="风声呼啸"))


def test_env_action_beat_is_fine():
    beat = _beat(owner="ENV", type="action", action=Action(stage="山门轰然洞开"))
    assert beat.as_text() == "山门轰然洞开"


def test_as_text_by_type():
    assert _beat(type="dialogue", dialogue=Dialogue(line="我要拜师")).as_text() == "char.ye_fan：我要拜师"
    assert _beat(type="thought", thought=Thought(inner="退无可退")).as_text() == "（退无可退）"
