"""MemoryStore：MemoryEntry —— 对应 docs/schema/stores/memory-store.md。

派生投影：有损、evidence 回指、软失效。M0 最小落地。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import CharTier, Resolution
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel, Temporal

MemType = Literal["fact", "belief", "trait", "voice", "ability", "goal"]
GoalKind = Literal["long-drive", "stage-goal"]


class MemoryEntry(SchemaModel, Temporal):
    """字段对齐 docs/schema/stores/memory-store.md。"""

    id: str                          # m.{ulid}
    type: MemType
    scope: str                       # char.{slug} | th.{slug} | global
    text: str
    t_valid: int = 0                 # as-of 生效章（主时钟）
    t_invalid: int | None = None     # 软失效章（None=仍有效）
    strength: float | None = None    # 信念/性格程度/执念（belief/trait/goal）
    evidence: list[EvidenceSpan] = Field(default_factory=list)  # 【必填】守 U
    involves: list[str] = Field(default_factory=list)  # 牵涉实体（fact，关系触发检索前提）
    salience: float = 0.5            # 显著度，抗 recency 淹没（fact）
    resolution: Resolution | None = None  # 软失效原因（goal/伏笔）
    # type 专属
    goal_kind: GoalKind | None = None
    parent: str | None = None        # goal 层级链，引用另一 m.{ulid}
    example: str | None = None       # voice 真实台词例句（few-shot 库）
    tier: CharTier = CharTier.T3     # 角色分层（画像完整度/检索降权）
    ability_rank: int | None = None  # ability 台阶序（修为单调硬检）
    vec: list[float] | None = None   # embedding；建在 text 上（M4 Embedder 写入）

    @classmethod
    def llm_vocab(cls) -> str:
        return (
            "MemoryEntry（入参旧记忆行）：\n"
            "- id: m.{ulid}；type: fact|belief|trait|voice|ability|goal\n"
            "- scope: char.{slug}|th.{slug}|global；text；t_valid\n"
            "- 抽取时 mem_ops.action 先 ADD；是否改成 REINFORCE 由下游对账。"
        )
