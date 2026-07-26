"""ScriptStore：ChapterScript / Scene / Beat —— 对应 docs/schema/stores/script-store.md。

主真相：只追加、永不改、过闸才进。字段对齐冻结文档全字段。
位置 id 沿用代码惯例 `chapter` / `scene_id` / `beat_id`（文档统称 id）。

Beat 两段结构是内容/流向分权的焊点：
  派工段（owner/dramatic_goal/hits）由 Director·dispatch 铸，持久化作证据链；
  实现段（type + dialogue/action/thought）由 Character 填。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from story_engine.primitives.evidence import StoryTime
from story_engine.schemas.base import SchemaModel

BeatType = Literal["dialogue", "action", "thought"]
HandoffKind = Literal["ADDRESS", "DEMAND", "EXIT", "NONE"]
ForeshadowOpName = Literal["PLANT", "REINFORCE", "FULFILL"]
ConsistencyStatus = Literal["clean", "flagged"]

# 非角色 owner：环境事件 / 旁白（不得有台词，见不变式 4）
NON_CHARACTER_OWNERS = frozenset({"ENV", "NARRATION"})


class Dialogue(SchemaModel):
    line: str
    subtext: str | None = None
    tone: str | None = None


class Action(SchemaModel):
    stage: str


class Thought(SchemaModel):
    inner: str


class Handoff(SchemaModel):
    """喂下一次 dispatch 的流向提示，非渲染字段。"""

    kind: HandoffKind = "NONE"
    target: str | None = None


class Beat(SchemaModel):
    """一拍 = 派工段 + 实现段。evidence 的主要落点，自身不带 evidence。"""

    beat_id: str                      # c{n}.s{m}.b{k}
    # —— 派工段（Director·dispatch）——
    owner: str                        # char.{slug} | ENV | NARRATION
    dramatic_goal: str                # 焊死：只含戏剧目标，禁台词
    hits: str | None = None           # 命中的承重拍 obligation_id
    # —— 实现段（Character）——
    type: BeatType
    dialogue: Dialogue | None = None
    action: Action | None = None
    thought: Thought | None = None
    # —— 流向 ——
    handoff: Handoff | None = None

    @model_validator(mode="after")
    def _check_payload(self) -> "Beat":
        payload = {"dialogue": self.dialogue, "action": self.action, "thought": self.thought}
        if payload[self.type] is None:
            raise ValueError(f"type={self.type} 的拍必须填 {self.type} 段")
        extra = [k for k, v in payload.items() if v is not None and k != self.type]
        if extra:
            raise ValueError(f"type={self.type} 的拍不得同时填 {extra}")
        if self.owner in NON_CHARACTER_OWNERS and self.type == "dialogue":
            raise ValueError(f"{self.owner} 拍不得有台词（仅 action/thought）")
        return self

    def as_text(self) -> str:
        """渲染成纯文本（供 Chunker/Writer/摘要消费）。"""
        if self.type == "dialogue" and self.dialogue:
            return f"{self.owner}：{self.dialogue.line}"
        if self.type == "action" and self.action:
            return self.action.stage
        if self.type == "thought" and self.thought:
            return f"（{self.thought.inner}）"
        return ""


class SceneCast(SchemaModel):
    char: str
    entry_state: str


class Scene(SchemaModel):
    scene_id: str                     # c{n}.s{m}
    location: str                     # loc.{slug}，硬检存在性
    pov: str                          # char.{slug}
    goal: str
    conflict: str
    contract_ref: str                 # 回指 SceneContract.scene_id
    time: StoryTime = Field(default_factory=StoryTime)
    mood: str = ""                    # 氛围/天气（VLM 用）
    cast: list[SceneCast] = Field(default_factory=list)
    beats: list[Beat] = Field(default_factory=list)


class ForeshadowOpRef(SchemaModel):
    """本章实际发生的伏笔操作（对账 ChapterPlan 的意图）。"""

    op: ForeshadowOpName
    fs_id: str


class ChapterScript(SchemaModel):
    chapter: str                      # c{n}，= as-of 主时钟
    volume: str                       # v{k}
    theme: str
    tone: str
    covered_threads: list[str] = Field(default_factory=list)     # th.{slug}[]
    foreshadow_ops: list[ForeshadowOpRef] = Field(default_factory=list)
    consistency_status: ConsistencyStatus = "clean"              # 过闸标记
    derived_from: str | None = None   # chapter_plan_ref
    scenes: list[Scene] = Field(default_factory=list)
