"""Script 三层的测试构造器。

ChapterScript/Scene/Beat 对齐冻结文档后必填字段较多，测试只关心其中一两个，
用这些 helper 填其余合法缺省，避免每个 UT 重复样板。
"""

from __future__ import annotations

from story_engine.schemas.stores.script import (
    Action,
    Beat,
    ChapterScript,
    Dialogue,
    Scene,
    Thought,
)


def make_beat(
    beat_id: str = "tmp",
    text: str = "他向前走了一步",
    *,
    owner: str = "char.ye_fan",
    dramatic_goal: str = "推进本场冲突",
    hits: str | None = None,
    kind: str = "action",
) -> Beat:
    payload: dict = {}
    if kind == "action":
        payload["action"] = Action(stage=text)
    elif kind == "dialogue":
        payload["dialogue"] = Dialogue(line=text)
    else:
        payload["thought"] = Thought(inner=text)
    return Beat(
        beat_id=beat_id,
        owner=owner,
        dramatic_goal=dramatic_goal,
        hits=hits,
        type=kind,  # type: ignore[arg-type]
        **payload,
    )


def make_scene(
    scene_id: str = "c1.s1",
    beats: list[Beat] | None = None,
    *,
    location: str = "loc.qing_yun",
    pov: str = "char.ye_fan",
    goal: str = "拜入宗门",
    conflict: str = "门规阻拦",
    contract_ref: str | None = None,
) -> Scene:
    return Scene(
        scene_id=scene_id,
        location=location,
        pov=pov,
        goal=goal,
        conflict=conflict,
        contract_ref=contract_ref or scene_id,
        beats=beats or [],
    )


def make_chapter_script(
    chapter: str = "c1",
    scenes: list[Scene] | None = None,
    *,
    volume: str = "v1",
    theme: str = "少年入门",
    tone: str = "热血",
) -> ChapterScript:
    return ChapterScript(
        chapter=chapter,
        volume=volume,
        theme=theme,
        tone=tone,
        scenes=scenes or [],
    )
