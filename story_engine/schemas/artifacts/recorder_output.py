"""RecorderOutput / MemOp / ArcOp —— 对应 docs/schema/artifacts/recorder-output.md。

Recorder（Extractor）抽取增量。**抽取是 LLM（M2），应用是确定性（M1 Applier）**。
字段严格对齐冻结文档（action 值集、target_id、strength/involves 等）。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import Resolution, WorldTier
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.memory import GoalKind, MemType
from story_engine.schemas.stores.world import WorldKind

MemAction = Literal["ADD", "REINFORCE", "SOFT-INVALIDATE", "NOOP"]
# world 演化域：登记新 minor / 更新 state（as-of 软失效，不删）
WorldOpName = Literal["REGISTER", "UPDATE_STATE", "SOFT-INVALIDATE", "NOOP"]
ArcOpName = Literal[
    "PLANT", "REINFORCE", "FULFILL", "ABANDON",   # fs/secret 状态机
    "REVEAL",                                       # secret 知情变更
    "ADVANCE", "CLIMAX", "RESOLVE", "DROP",         # thread 进度
    "NOOP",
]


class MemOp(SchemaModel):
    """对 MemoryStore 的一步操作，字段对齐 memory-store。"""

    action: MemAction
    target_id: str | None = None           # REINFORCE/SOFT-INVALIDATE 必填，指既有 m.{ulid}
    # —— 条目载荷（ADD 必填）——
    type: MemType | None = None
    scope: str | None = None               # char.{slug} | th.{slug} | global
    text: str | None = None
    strength: float | None = None
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    involves: list[str] = Field(default_factory=list)           # fact
    salience: float = 0.5                                       # fact
    goal_kind: GoalKind | None = None
    parent: str | None = None
    example: str | None = None
    resolution: Resolution | None = None   # 配 SOFT-INVALIDATE：achieved|abandoned|superseded

    @classmethod
    def llm_vocab(cls) -> str:
        return (
            "MemOp（人物/事实进 MemoryStore，角色用这个，不要进 world_ops）：\n"
            "- action: ADD | REINFORCE | SOFT-INVALIDATE | NOOP\n"
            "- 抽取阶段 action 一律先填 ADD（是否加强/失效由下游 Reconciler 定）。\n"
            "- type: fact | belief | trait | voice | ability | goal\n"
            "- scope: char.{slug} | th.{slug} | global\n"
            "- goal_kind?: long-drive | stage-goal\n"
            "- resolution?（配 SOFT-INVALIDATE）: achieved | abandoned | superseded\n"
            f"- evidence: {EvidenceSpan.llm_vocab()}"
        )


class ArcOp(SchemaModel):
    """对 ArcStore 台账的一步操作（状态机转移），字段对齐 arc-store。"""

    target_id: str                         # fs.{slug} | sec.{slug} | th.{slug}
    kind: Literal["foreshadow", "secret", "thread"] = "foreshadow"
    op: ArcOpName
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    abandon_reason: str | None = None      # ABANDON/DROP 必填
    reveal_to: list[str] = Field(default_factory=list)          # REVEAL：新增知情人
    milestone: str | None = None           # ADVANCE 描述
    is_new: bool = False                   # emergent 提名（新建 record）
    draft: dict | None = None              # 新建时草稿定义 {desc, kind, importance?, tier?}

    @classmethod
    def llm_vocab(cls) -> str:
        return (
            "ArcOp（伏笔/秘密/主线台账转移）：\n"
            "- target_id: fs.{slug} | sec.{slug} | th.{slug}\n"
            "- kind: foreshadow | secret | thread\n"
            "- op（按 kind）：\n"
            "  · foreshadow/secret: PLANT | REINFORCE | FULFILL | ABANDON | NOOP"
            "（secret 另有 REVEAL）\n"
            "  · thread: ADVANCE | CLIMAX | RESOLVE | DROP | NOOP\n"
            "- 状态机（必须遵守当前台账 state，见入参「伏笔/主线台账」）：\n"
            "  · foreshadow/secret: PLANNED -PLANT→ PLANTED -REINFORCE→ REINFORCED "
            "-FULFILL→ FULFILLED；ABANDON 终态\n"
            "  · **禁止**对 PLANNED 发 REINFORCE/FULFILL（须先 PLANT）\n"
            "  · thread: OPEN -ADVANCE→ ADVANCING -CLIMAX→ CLIMAX -RESOLVE→ RESOLVED\n"
            "- 台账已有 id：用原 id，is_new=false；本章新冒出：is_new=true + draft.desc\n"
            f"- evidence: {EvidenceSpan.llm_vocab()}"
        )


class WorldOp(SchemaModel):
    """对 WorldStore 的一步操作：minor 登记 + 演化域 state as-of。

    字段对齐 docs/schema/artifacts/recorder-output.md WorldOp。
    """

    entity_id: str                         # concept.|art.|loc.|org.|item.|race.{slug}
    op: WorldOpName
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    # —— REGISTER：现场造出的长尾实体登记（默认 minor）——
    canonical_name: str | None = None
    tier: WorldTier = WorldTier.MINOR
    definition: str | None = None          # minor 轻量自动抽取
    aliases: list[str] = Field(default_factory=list)
    kind: WorldKind | None = None          # 与 WorldEntity 同枚举；角色禁止进 world_ops
    # —— UPDATE_STATE：演化域（势力覆灭、据点易主…）——
    state: dict = Field(default_factory=dict)

    @classmethod
    def llm_vocab(cls) -> str:
        return (
            "WorldOp（世界设定进 WorldStore；**禁止角色**）：\n"
            "- op: REGISTER | UPDATE_STATE | SOFT-INVALIDATE | NOOP\n"
            "- entity_id 前缀仅限: concept. | art. | loc. | org. | item. | race.\n"
            "- kind 仅限: concept | art | location | faction | item | race\n"
            "  （loc.↔location，org.↔faction；kind 与前缀必须一致）\n"
            "- tier: core | major | minor（默认 minor）\n"
            "- **禁止** kind=character / entity_id=char.* —— 人物事实走 MemOp(scope=char.*)\n"
            f"- evidence: {EvidenceSpan.llm_vocab()}"
        )


class TierNom(SchemaModel):
    """人物分级提名（Replanner 卷末确认）。`from`/`to` 是保留字，故加 _tier 后缀。"""

    char: str                              # char.{slug}
    from_tier: int
    to_tier: int
    reason: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)

    @classmethod
    def llm_vocab(cls) -> str:
        return (
            "TierNom（人物分级提名，极少用）：\n"
            "- char: char.{slug}\n"
            "- from_tier / to_tier: 0|1|2|3（数字越小越高）\n"
            f"- evidence: {EvidenceSpan.llm_vocab()}"
        )


class RecorderOutput(SchemaModel):
    """一章抽取的完整增量，Applier 原子应用。"""

    chapter: int
    mem_ops: list[MemOp] = Field(default_factory=list)
    arc_ops: list[ArcOp] = Field(default_factory=list)
    world_ops: list[WorldOp] = Field(default_factory=list)
    tier_noms: list[TierNom] = Field(default_factory=list)
    extractor_version: str | None = None

    @classmethod
    def llm_vocab(cls) -> str:
        return "\n\n".join(
            [
                "【输出契约 RecorderOutput】必须输出符合本结构的 JSON；关键取值如下：",
                MemOp.llm_vocab(),
                ArcOp.llm_vocab(),
                WorldOp.llm_vocab(),
                TierNom.llm_vocab(),
            ]
        )
