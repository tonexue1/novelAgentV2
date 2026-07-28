"""D2 阶梯健康 —— ViolationLog + RunRecord.verdict。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from story_engine.schemas.stores.violation import Violation
from story_engine.telemetry.runrecord import RunRecord


class D2Metrics(BaseModel):
    available: bool = False
    total: int = 0
    by_resolution: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_escalation_level: dict[str, int] = Field(default_factory=dict)
    open_count: int = 0
    flagged_count: int = 0
    blocked_count: int = 0
    retry_count_sum: int = 0
    escalate_volume_count: int = 0
    runrecord_verdicts: dict[str, int] = Field(default_factory=dict)


def compute_d2(
    violations: list[Violation] | None,
    *,
    available: bool,
    records: list[RunRecord] | None = None,
) -> D2Metrics:
    if not available and not records:
        return D2Metrics(available=False)

    by_res: dict[str, int] = {}
    by_sev: dict[str, int] = {}
    by_esc: dict[str, int] = {}
    open_n = flagged_n = blocked_n = 0
    retry_sum = 0
    vol_n = 0
    violations = violations or []

    for v in violations:
        res = v.resolution
        by_res[res] = by_res.get(res, 0) + 1
        sev = v.severity.value if hasattr(v.severity, "value") else str(v.severity)
        by_sev[sev] = by_sev.get(sev, 0) + 1
        by_esc[v.escalation_level] = by_esc.get(v.escalation_level, 0) + 1
        if res == "open":
            open_n += 1
        elif res == "flagged":
            flagged_n += 1
        elif res == "blocked":
            blocked_n += 1
        retry_sum += v.retry_count
        if v.escalation_level == "volume":
            vol_n += 1

    verdicts: dict[str, int] = {}
    for r in records or []:
        if r.verdict:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
            if r.verdict.upper() in {"ESCALATE_VOLUME", "ESCALATE-VOLUME"}:
                vol_n += 1

    return D2Metrics(
        available=bool(available or records),
        total=len(violations),
        by_resolution=by_res,
        by_severity=by_sev,
        by_escalation_level=by_esc,
        open_count=open_n,
        flagged_count=flagged_n,
        blocked_count=blocked_n,
        retry_count_sum=retry_sum,
        escalate_volume_count=vol_n,
        runrecord_verdicts=verdicts,
    )
