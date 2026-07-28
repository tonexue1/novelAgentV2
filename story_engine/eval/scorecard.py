"""Scorecard：一次 run 的聚合报告。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from story_engine.eval.load import RunArtifacts, infer_as_of, load_run
from story_engine.eval.metrics_c2 import C2Metrics, ScriptGateMetrics, compute_c2, compute_script_gate
from story_engine.eval.metrics_d2 import D2Metrics, compute_d2
from story_engine.eval.metrics_e import EMetrics, compute_e


class Scorecard(BaseModel):
    run_dir: str
    runs_path: str | None = None
    as_of_chapter: int | None = None
    e: EMetrics = Field(default_factory=EMetrics)
    d2: D2Metrics = Field(default_factory=D2Metrics)
    c2: C2Metrics = Field(default_factory=C2Metrics)
    script_gate: ScriptGateMetrics = Field(default_factory=ScriptGateMetrics)


def build_scorecard(
    art: RunArtifacts,
    *,
    as_of: int | None = None,
) -> Scorecard:
    resolved_as_of = as_of if as_of is not None else infer_as_of(art.scripts)
    return Scorecard(
        run_dir=str(art.run_dir),
        runs_path=str(art.runs_path) if art.runs_path else None,
        as_of_chapter=resolved_as_of,
        e=compute_e(art.records, available=art.has_runs),
        d2=compute_d2(
            art.violations,
            available=art.has_violation,
            records=art.records if art.has_runs else None,
        ),
        c2=compute_c2(art.arcs, available=art.has_arc, as_of=resolved_as_of),
        script_gate=compute_script_gate(art.scripts, available=art.has_script),
    )


def scorecard_from_run(
    run_dir: str | Path,
    *,
    runs_path: str | Path | None = None,
    as_of: int | None = None,
) -> Scorecard:
    return build_scorecard(load_run(run_dir, runs_path=runs_path), as_of=as_of)


def render_scorecard(sc: Scorecard) -> str:
    lines = [
        f"# scorecard  run={sc.run_dir}",
        f"  runs_path={sc.runs_path or '(none)'}  as_of={sc.as_of_chapter}",
        "",
    ]
    e = sc.e
    if e.available:
        lines += [
            "## E 成本/延迟",
            f"  calls={e.calls}  tokens={e.total_tokens}  "
            f"cost_usd={e.cost_usd}  latency_ms_mean={e.latency_ms_mean}",
        ]
        if e.by_node:
            lines.append("  by_node:")
            for name, b in e.by_node.items():
                lines.append(
                    f"    {name}: calls={b.calls} tokens={b.total_tokens} "
                    f"cost={b.cost_usd} lat_mean={b.latency_ms_mean}"
                )
        if e.by_model:
            lines.append("  by_model:")
            for name, b in e.by_model.items():
                lines.append(
                    f"    {name}: calls={b.calls} tokens={b.total_tokens} cost={b.cost_usd}"
                )
        if e.verdict_counts:
            lines.append(f"  verdicts={e.verdict_counts}")
    else:
        lines += ["## E 成本/延迟", "  (n/a — 无 runs.jsonl)"]

    d2 = sc.d2
    lines.append("")
    if d2.available:
        lines += [
            "## D2 阶梯",
            f"  violations={d2.total}  open={d2.open_count}  "
            f"flagged={d2.flagged_count}  blocked={d2.blocked_count}",
            f"  retry_sum={d2.retry_count_sum}  escalate_volume={d2.escalate_volume_count}",
            f"  by_resolution={d2.by_resolution}",
            f"  by_escalation={d2.by_escalation_level}",
        ]
    else:
        lines += ["## D2 阶梯", "  (n/a — 无 violation.jsonl)"]

    c2 = sc.c2
    lines.append("")
    if c2.available:
        lines += [
            "## C2 伏笔",
            f"  total={c2.foreshadow_total}  active={c2.foreshadow_active}  "
            f"fulfilled={c2.foreshadow_fulfilled}  abandoned={c2.foreshadow_abandoned}",
            f"  closed_rate={c2.closed_rate}  settled_rate={c2.settled_rate}",
            f"  due={c2.due_count}  overdue={c2.overdue_count}  "
            f"core_overdue={c2.core_overdue_count}  (as_of={c2.as_of_chapter})",
        ]
    else:
        lines += ["## C2 伏笔", "  (n/a — 无 arc.jsonl)"]

    sg = sc.script_gate
    lines.append("")
    if sg.available:
        lines += [
            "## Script 闸门",
            f"  chapters={sg.chapters}  clean={sg.clean}  flagged={sg.flagged}",
        ]
        if sg.other:
            lines.append(f"  other={sg.other}")
    else:
        lines += ["## Script 闸门", "  (n/a — 无 script.jsonl)"]

    return "\n".join(lines)


def scorecard_json(sc: Scorecard) -> str:
    return json.dumps(sc.model_dump(mode="json"), ensure_ascii=False, indent=2)
