"""SceneScript（场景合同）+ BeatDispatch（派工）—— 对应 docs/schema/artifacts/scene-script.md。

核心：**定锚（obligations）不定序**，turn 顺序运行时由 dispatch 涌现。
合同被 Scene.contract_ref 回指，供 Critic 验承重拍履约。
BeatDispatch 瞬态，不单独落库——Character 填实现段后由 Applier 合进 Beat 派工段。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.evidence import EvidenceSpan, StoryTime
from story_engine.schemas.base import SchemaModel

ForeshadowOpName = Literal["PLANT", "REINFORCE", "FULFILL"]


class ObligationBinding(SchemaModel):
    """承重拍绑定的伏笔/主线 op。"""

    op: ForeshadowOpName
    fs_id: str


class Obligation(SchemaModel):
    """承重拍：本场必命中的锚。无序，precede 只是软约束。"""

    obligation_id: str                                          # c{n}.s{m}.o{k}
    desc: str                                                   # 焊死：禁台词
    owner_hint: str | None = None                               # 建议主导者（非强制）
    precede: list[str] = Field(default_factory=list)            # 偏序软约束
    binds: ObligationBinding | None = None


class ContractCast(SchemaModel):
    char: str
    entry_state: str
    scene_goal: str | None = None                               # 场级动机


class SceneBudget(SchemaModel):
    max_beats: int | None = None                                # 撞预算强制收场


class SceneContract(SchemaModel):
    scene_id: str                                               # c{n}.s{m}
    location: str                                               # loc.{slug}
    pov: str                                                    # char.{slug}
    goal: str
    conflict: str
    time: StoryTime = Field(default_factory=StoryTime)
    cast: list[ContractCast] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    exit_when: list[str] = Field(default_factory=list)          # 退出条件（LLM 判，硬检兜底）
    budget: SceneBudget = Field(default_factory=SceneBudget)
    grounding: list[EvidenceSpan] = Field(default_factory=list)


class SceneScript(SchemaModel):
    chapter: str                                                # c{n}
    derived_from: str | None = None                             # chapter_plan_ref
    scenes: list[SceneContract] = Field(default_factory=list)


class BeatDispatch(SchemaModel):
    """逐拍派工，瞬态。dramatic_goal 焊死禁台词。"""

    scene: str                                                  # c{n}.s{m}
    owner: str                                                  # char.{slug} | ENV | NARRATION
    dramatic_goal: str
    hits: str | None = None                                     # 本拍要命中的承重拍
    directive: str | None = None                                # 额外调度提示（简短）
