"""ViolationLog：Violation —— 对应 docs/schema/stores/violation-log.md。

Hard-Check / Continuity Critic 的产物 + 升级阶梯生命周期。字段以文档为权威。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel

Stage = Literal["planner", "director·setup", "director·dispatch", "character"]
"""犯规发生在哪个生成阶段。Critic 评的是 Character 产物，故也记 character。"""

CheckType = Literal["hard", "llm"]

Category = Literal[
    "alive_present",
    "location",
    "timeline",
    "ability",
    "ref_integrity",
    "foreshadow_order",
    "POV",
    "OOC",
    "canon_contradiction",
    "voice",
    "logic",
    "other",
]

EscalationLevel = Literal["beat", "scene", "chapter", "volume"]

ResolutionState = Literal["open", "fixed", "flagged", "blocked", "advised"]


class Locus(SchemaModel):
    """犯规落点（位置 id 串）。"""

    chapter: str  # c{n}
    scene: str | None = None  # c{n}.s{m}
    beat: str | None = None  # c{n}.s{m}.b{k}
    obligation: str | None = None  # c{n}.s{m}.o{k}


class EscalationStep(SchemaModel):
    """阶梯轨迹一格。"""

    level: EscalationLevel
    attempt: int
    outcome: str


class Violation(SchemaModel):
    id: str  # vio.{ulid}
    chapter: int  # 发现于哪一章（as-of 主时钟）
    stage: Stage
    check_type: CheckType
    severity: Severity
    category: Category
    locus: Locus | None = None
    script_evidence: list[EvidenceSpan] = Field(default_factory=list)  # 犯处
    refs: list[str] = Field(default_factory=list)  # 被违背的既有条目 id
    message: str
    suggestion: str | None = None
    # —— 升级阶梯生命周期 ——
    escalation_level: EscalationLevel = "beat"
    retry_count: int = 0
    resolution: ResolutionState = "open"
    history: list[EscalationStep] = Field(default_factory=list)
