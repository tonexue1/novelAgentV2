"""ScriptStore：ChapterScript / Scene / Beat —— 对应 docs/schema/stores/script-store.md。

主真相：只追加、永不改、过闸才进。M0 最小落地。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.schemas.base import SchemaModel


class Beat(SchemaModel):
    beat_id: str            # c{n}.s{m}.b{k}
    pov: str | None = None
    content: str
    speakers: list[str] = Field(default_factory=list)


class Scene(SchemaModel):
    scene_id: str           # c{n}.s{m}
    goal: str | None = None
    location: str | None = None
    participants: list[str] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)


class ChapterScript(SchemaModel):
    chapter: str            # c{n}
    title: str | None = None
    scenes: list[Scene] = Field(default_factory=list)
    derived_from: dict | None = None    # ChapterPlan 追溯
