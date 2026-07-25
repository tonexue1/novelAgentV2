"""ViolationLog：Violation —— 对应 docs/schema/stores/violation-log.md。

Hard-Check / Critic 的产物 + 升级阶梯生命周期。M1 落地 Hard-Check 所需字段。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel


class Violation(SchemaModel):
    vio_id: str                       # vio.{ulid}
    rule: str                         # 触发的规则名，如 "ability_monotonic"
    severity: Severity
    detail: str
    chapter: int                      # 发现于哪一章（as-of）
    subject: str | None = None        # 涉及实体（char/arc/world id）
    evidence: list[EvidenceSpan] = Field(default_factory=list)
    status: str = "OPEN"              # OPEN | RETRYING | RESOLVED | ESCALATED | ADVISORY_LOGGED
