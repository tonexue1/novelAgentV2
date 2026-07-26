"""ChapterPlan（L3）—— 对应 docs/schema/artifacts/chapter-plan.md。

Planner 每章产。把 L2 粗章槽落成本章可执行方向，喂 Director·setup 拆场。
**只到章级义务，不映射到场**（拆场是 Director 的活）。

命名卫生（三个"拍"层层细化）：
  story_beats（章内桥段，Planner）→ obligation（场内锚，Director）→ Beat（一拍，Character）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.schemas.base import SchemaModel

ForeshadowOpName = Literal["PLANT", "REINFORCE", "FULFILL"]
ForeshadowReason = Literal["due", "overdue", "organic"]


class PlanDerivedFrom(SchemaModel):
    """追溯链，供卷复盘做漂移度量。"""

    l2_vol_id: str                                              # v{k}
    planned_seq: int | None = None
    l1_thread_ids: list[str] = Field(default_factory=list)
    l1_fs_ids: list[str] = Field(default_factory=list)


class ThreadAdvanceIntent(SchemaModel):
    thread_id: str
    intent: str                                                 # 推进到什么程度
    milestone_ref: str | None = None


class ForeshadowOpPlan(SchemaModel):
    fs_id: str
    op: ForeshadowOpName
    reason: ForeshadowReason                                    # due | overdue | organic


class CastMember(SchemaModel):
    """required=true 硬性出场（Director 不得删）；false 为建议，Director 可裁。"""

    char_id: str
    role_in_chapter: str
    required: bool = True


class StoryBeat(SchemaModel):
    """章内粗桥段（Director 拆场骨架），非 Script.Beat。"""

    seq: int
    gist: str


class ChapterPlan(SchemaModel):
    chapter: str                                                # c{n}
    derived_from: PlanDerivedFrom
    theme: str
    tone: str
    chapter_goal: str                                           # 章级收敛判据
    thread_advances: list[ThreadAdvanceIntent] = Field(default_factory=list)
    foreshadow_ops: list[ForeshadowOpPlan] = Field(default_factory=list)
    cast: list[CastMember] = Field(default_factory=list)
    background_hint: str | None = None                          # 群体占位，交 Director 填充+命名
    entries: list[str] = Field(default_factory=list)            # char.{slug}[]，本章进场
    exits: list[str] = Field(default_factory=list)              # char.{slug}[]，本章退场
    story_beats: list[StoryBeat] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)        # 硬约束
