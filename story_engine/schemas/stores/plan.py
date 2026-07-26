"""PlanStore：L0 / L1 / L2 —— 对应 docs/schema/stores/plan-store.md。

M0 落地范围：Gate + smoke 需要的字段。完整字段以文档为准，逐步补齐。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import DetailLevel, Importance
from story_engine.schemas.base import SchemaModel


class L0(SchemaModel):
    """立意，单例、创世冻结；改=换书。纯文字无 id。"""

    logline: str
    genre: list[str] = Field(default_factory=list)
    themes: list[str] = Field(default_factory=list)
    tone: list[str] = Field(default_factory=list)
    target_length: str | None = None
    media: str = "novel"
    core_dramatic_question: str
    ending_intent: str
    protagonist_arc_intent: list[str] = Field(default_factory=list)


class Milestone(SchemaModel):
    desc: str
    target_vol: str | None = None


class Thread(SchemaModel):
    thread_id: str  # th.{slug}
    tier: Literal["main", "saga", "local"]
    parent_thread_id: str | None = None
    desc: str
    start_ch: int | None = None
    target_ch: int | None = None
    milestones: list[Milestone] = Field(default_factory=list)


class CharacterArc(SchemaModel):
    """仅收录 tier 0/1。"""

    char_id: str  # char.{slug}
    from_state: str
    to_state: str
    key_shifts: list[str] = Field(default_factory=list)


class PayoffDeadline(SchemaModel):
    granularity: Literal["chapter", "volume", "saga"]
    ref: str


class Foreshadow(SchemaModel):
    fs_id: str  # fs.{slug}
    desc: str
    plant_range: str | None = None
    payoff_deadline: PayoffDeadline | None = None
    importance: Importance = Importance.MINOR


class Saga(SchemaModel):
    saga_id: str  # sg{k}
    title: str
    volume_range: str | None = None
    goal: str | None = None
    saga_turning_point: str | None = None
    detail_level: DetailLevel = DetailLevel.SKETCH


class Volume(SchemaModel):
    vol_id: str  # v{k}
    saga_id: str | None = None
    title: str
    chapter_range: str | None = None
    goal: str | None = None
    detail_level: DetailLevel = DetailLevel.SKETCH


class L1(SchemaModel):
    """全书结构，整份快照版本化；防漂移主锚。"""

    version: int = 1
    created_at_ch: int = 0
    status: str = "active"
    sagas: list[Saga] = Field(default_factory=list)
    volumes: list[Volume] = Field(default_factory=list)
    threads: list[Thread] = Field(default_factory=list)
    character_arcs: list[CharacterArc] = Field(default_factory=list)
    turning_points: list[Milestone] = Field(default_factory=list)
    foreshadow_map: list[Foreshadow] = Field(default_factory=list)
    # L1 点名依赖的承重 canon（world id）；创世 Gate 闭包检查的显式依据。
    # 见 docs/schema/stores/plan-store.md「world_refs 显式化」。
    world_refs: list[str] = Field(default_factory=list)


class ThreadTarget(SchemaModel):
    thread_id: str
    target_milestone: str


class ForeshadowDue(SchemaModel):
    fs_id: str
    action: Literal["plant", "fulfill"]


SpineTouch = Literal["pressure", "inciting", "midpoint", "climax", "bridge"]


class VolumeSpine(SchemaModel):
    """卷级戏剧脊骨：先于分章；人物人设不进这里。"""

    shared_pressure: str
    inciting: str
    midpoint: str
    climax: str


class ChapterBeat(SchemaModel):
    """粗章事件节点（事件链），不绑 c{n}；连续性靠 inherits/leaves_open。"""

    planned_seq: int
    event: str
    leaves_open: list[str] = Field(default_factory=list)
    inherits: list[str] = Field(default_factory=list)
    touches_spine: SpineTouch = "bridge"
    pov_focus: list[str] = Field(default_factory=list)


class L2(SchemaModel):
    """每卷，滚动生成。"""

    vol_id: str
    version: int = 1
    goal: str | None = None
    thread_targets: list[ThreadTarget] = Field(default_factory=list)
    foreshadow_due: list[ForeshadowDue] = Field(default_factory=list)
    volume_spine: VolumeSpine | None = None
    chapter_beats: list[ChapterBeat] = Field(default_factory=list)
