"""A/B compare：并排 Δ，不自动判胜负。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from story_engine.eval.scorecard import Scorecard


def _pct(a: float | int | None, b: float | int | None) -> float | None:
    if a is None or b is None:
        return None
    if float(a) == 0:
        return None
    return round((float(b) - float(a)) / float(a) * 100.0, 2)


def _delta(a: float | int | None, b: float | int | None) -> float | None:
    if a is None or b is None:
        return None
    raw = float(b) - float(a)
    if isinstance(a, int) and isinstance(b, int):
        return int(raw)
    return round(raw, 6)


class MetricDelta(BaseModel):
    key: str
    a: float | int | None = None
    b: float | int | None = None
    delta: float | None = None
    delta_pct: float | None = None


class CompareReport(BaseModel):
    a_run: str
    b_run: str
    deltas: list[MetricDelta] = Field(default_factory=list)


def _pair(key: str, a: Any, b: Any) -> MetricDelta:
    return MetricDelta(key=key, a=a, b=b, delta=_delta(a, b), delta_pct=_pct(a, b))


def compare_scorecards(a: Scorecard, b: Scorecard) -> CompareReport:
    deltas: list[MetricDelta] = []

    if a.e.available and b.e.available:
        deltas += [
            _pair("e.calls", a.e.calls, b.e.calls),
            _pair("e.total_tokens", a.e.total_tokens, b.e.total_tokens),
            _pair("e.cost_usd", a.e.cost_usd, b.e.cost_usd),
            _pair("e.latency_ms_mean", a.e.latency_ms_mean, b.e.latency_ms_mean),
        ]

    if a.d2.available and b.d2.available:
        deltas += [
            _pair("d2.total", a.d2.total, b.d2.total),
            _pair("d2.open", a.d2.open_count, b.d2.open_count),
            _pair("d2.flagged", a.d2.flagged_count, b.d2.flagged_count),
            _pair("d2.blocked", a.d2.blocked_count, b.d2.blocked_count),
            _pair("d2.retry_sum", a.d2.retry_count_sum, b.d2.retry_count_sum),
            _pair("d2.escalate_volume", a.d2.escalate_volume_count, b.d2.escalate_volume_count),
        ]

    if a.c2.available and b.c2.available:
        deltas += [
            _pair("c2.closed_rate", a.c2.closed_rate, b.c2.closed_rate),
            _pair("c2.overdue", a.c2.overdue_count, b.c2.overdue_count),
            _pair("c2.core_overdue", a.c2.core_overdue_count, b.c2.core_overdue_count),
            _pair("c2.active", a.c2.foreshadow_active, b.c2.foreshadow_active),
        ]

    if a.script_gate.available and b.script_gate.available:
        deltas += [
            _pair("script.clean", a.script_gate.clean, b.script_gate.clean),
            _pair("script.flagged", a.script_gate.flagged, b.script_gate.flagged),
        ]

    return CompareReport(a_run=a.run_dir, b_run=b.run_dir, deltas=deltas)


def render_compare(rep: CompareReport) -> str:
    lines = [
        f"# compare  A={rep.a_run}",
        f"#          B={rep.b_run}",
        f"{'key':<28} {'A':>12} {'B':>12} {'Δ':>12} {'Δ%':>10}",
        "-" * 76,
    ]
    for d in rep.deltas:
        a_s = "-" if d.a is None else str(d.a)
        b_s = "-" if d.b is None else str(d.b)
        delta_s = "-" if d.delta is None else str(d.delta)
        pct_s = "-" if d.delta_pct is None else f"{d.delta_pct}%"
        lines.append(f"{d.key:<28} {a_s:>12} {b_s:>12} {delta_s:>12} {pct_s:>10}")
    lines.append("")
    lines.append("（不自动判胜负；成本↓ / 违规↑ / core_overdue↑ 需人工解读）")
    return "\n".join(lines)


def compare_json(rep: CompareReport) -> str:
    return json.dumps(rep.model_dump(mode="json"), ensure_ascii=False, indent=2)
