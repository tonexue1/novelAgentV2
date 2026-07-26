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


class WorldOp(SchemaModel):
    """对 WorldStore 的一步操作：minor 登记 + 演化域 state as-of。

    冻结文档只写「WorldOp 见 world-store 演化域」，未给精确字段表；
    此处按该节推导（登记 / 改 state / 软失效），待评审。
    """

    entity_id: str                         # concept.|art.|loc.|org.|item.|race.{slug}
    op: WorldOpName
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    # —— REGISTER：现场造出的长尾实体登记（默认 minor）——
    canonical_name: str | None = None
    tier: WorldTier = WorldTier.MINOR
    definition: str | None = None          # minor 轻量自动抽取
    aliases: list[str] = Field(default_factory=list)
    # —— UPDATE_STATE：演化域（势力覆灭、据点易主…）——
    state: dict = Field(default_factory=dict)


class TierNom(SchemaModel):
    """人物分级提名（Replanner 卷末确认）。`from`/`to` 是保留字，故加 _tier 后缀。"""

    char: str                              # char.{slug}
    from_tier: int
    to_tier: int
    reason: str
    evidence: list[EvidenceSpan] = Field(default_factory=list)


class RecorderOutput(SchemaModel):
    """一章抽取的完整增量，Applier 原子应用。"""

    chapter: int
    mem_ops: list[MemOp] = Field(default_factory=list)
    arc_ops: list[ArcOp] = Field(default_factory=list)
    world_ops: list[WorldOp] = Field(default_factory=list)
    tier_noms: list[TierNom] = Field(default_factory=list)
    extractor_version: str | None = None
