"""M5a：离线 scorecard / compare UT。"""

from __future__ import annotations

from pathlib import Path

from story_engine.eval.compare import compare_scorecards
from story_engine.eval.scorecard import scorecard_from_run
from story_engine.primitives.enums import Importance, Severity
from story_engine.primitives.ids import mint_violation_id
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.plan import PayoffDeadline
from story_engine.schemas.stores.script import ChapterScript
from story_engine.schemas.stores.violation import Violation
from story_engine.telemetry.runrecord import RunRecord


def _write_jsonl(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(r.model_dump_json() + "\n")


def _make_run(tmp: Path, name: str) -> Path:
    root = tmp / name
    stores = root / "stores"
    stores.mkdir(parents=True)

    records = [
        RunRecord(
            node="director_setup",
            model="deepseek-v4-pro",
            prompt_tokens=100,
            completion_tokens=50,
            cost_usd=0.01,
            latency_ms=200.0,
            chapter=1,
        ),
        RunRecord(
            node="character",
            model="deepseek-v4-flash",
            prompt_tokens=80,
            completion_tokens=40,
            cost_usd=0.002,
            latency_ms=50.0,
            chapter=1,
            verdict="PASS",
        ),
    ]
    _write_jsonl(root / "runs.jsonl", records)

    arcs = [
        ArcRecord(
            id="fs.closed",
            kind="foreshadow",
            desc="已收",
            importance=Importance.MAJOR,
            state="FULFILLED",
            payoff_deadline=PayoffDeadline(granularity="chapter", ref="c2"),
        ),
        ArcRecord(
            id="fs.open",
            kind="foreshadow",
            desc="未收",
            importance=Importance.CORE,
            state="PLANTED",
            payoff_deadline=PayoffDeadline(granularity="chapter", ref="c2"),
        ),
        ArcRecord(
            id="th.main",
            kind="thread",
            desc="主线",
            thread_state="OPEN",
            tier="main",
        ),
    ]
    _write_jsonl(stores / "arc.jsonl", arcs)

    vios = [
        Violation(
            id=mint_violation_id(),
            chapter=1,
            stage="character",
            check_type="hard",
            severity=Severity.CORRECT,
            category="timeline",
            message="x",
            resolution="flagged",
            escalation_level="scene",
            retry_count=2,
        ),
        Violation(
            id=mint_violation_id(),
            chapter=2,
            stage="character",
            check_type="llm",
            severity=Severity.BLOCK,
            category="OOC",
            message="y",
            resolution="blocked",
            escalation_level="volume",
            retry_count=1,
        ),
    ]
    _write_jsonl(stores / "violation.jsonl", vios)

    scripts = [
        ChapterScript(
            chapter="c1",
            volume="v1",
            theme="t",
            tone="t",
            consistency_status="clean",
        ),
        ChapterScript(
            chapter="c3",
            volume="v1",
            theme="t",
            tone="t",
            consistency_status="flagged",
        ),
    ]
    _write_jsonl(stores / "script.jsonl", scripts)
    return root


def test_scorecard_aggregates(tmp_path: Path):
    root = _make_run(tmp_path, "base")
    sc = scorecard_from_run(root)

    assert sc.as_of_chapter == 3
    assert sc.e.available
    assert sc.e.calls == 2
    assert sc.e.total_tokens == 270
    assert sc.e.cost_usd == 0.012
    assert "director_setup" in sc.e.by_node
    assert "deepseek-v4-flash" in sc.e.by_model

    assert sc.d2.available
    assert sc.d2.total == 2
    assert sc.d2.flagged_count == 1
    assert sc.d2.blocked_count == 1
    assert sc.d2.retry_count_sum == 3
    assert sc.d2.escalate_volume_count == 1

    assert sc.c2.available
    assert sc.c2.foreshadow_total == 2
    assert sc.c2.foreshadow_fulfilled == 1
    assert sc.c2.foreshadow_active == 1
    assert sc.c2.closed_rate == 0.5
    # as_of=3 ≥ deadline c2 → open core is overdue
    assert sc.c2.overdue_count == 1
    assert sc.c2.core_overdue_count == 1

    assert sc.script_gate.chapters == 2
    assert sc.script_gate.clean == 1
    assert sc.script_gate.flagged == 1


def test_missing_files_na(tmp_path: Path):
    root = tmp_path / "empty"
    (root / "stores").mkdir(parents=True)
    sc = scorecard_from_run(root)
    assert not sc.e.available
    assert not sc.d2.available
    assert not sc.c2.available
    assert not sc.script_gate.available


def test_as_of_override(tmp_path: Path):
    root = _make_run(tmp_path, "asof")
    sc = scorecard_from_run(root, as_of=1)
    # deadline c2, as_of=1 → due window (chapter_window=2): 2-2=0 ≤ 1 < 2 → due
    assert sc.c2.as_of_chapter == 1
    assert sc.c2.overdue_count == 0
    assert sc.c2.due_count == 1


def test_compare_deltas(tmp_path: Path):
    a_root = _make_run(tmp_path, "a")
    b_root = _make_run(tmp_path, "b")
    # cheapen B: rewrite runs with half tokens
    cheap = [
        RunRecord(
            node="director_setup",
            model="deepseek-v4-flash",
            prompt_tokens=50,
            completion_tokens=25,
            cost_usd=0.004,
            latency_ms=80.0,
        ),
    ]
    _write_jsonl(b_root / "runs.jsonl", cheap)

    a = scorecard_from_run(a_root)
    b = scorecard_from_run(b_root)
    rep = compare_scorecards(a, b)
    by_key = {d.key: d for d in rep.deltas}
    assert by_key["e.calls"].a == 2
    assert by_key["e.calls"].b == 1
    assert by_key["e.calls"].delta == -1
    assert by_key["e.cost_usd"].delta is not None
    assert by_key["e.cost_usd"].delta < 0
    assert by_key["c2.core_overdue"].delta == 0


def test_cli_report(tmp_path: Path, capsys):
    from story_engine.eval.__main__ import main

    root = _make_run(tmp_path, "cli")
    main(["report", "--run", str(root)])
    out = capsys.readouterr().out
    assert "scorecard" in out
    assert "E 成本" in out
    assert "C2 伏笔" in out

    main(["compare", "--a", str(root), "--b", str(root), "--json"])
    out2 = capsys.readouterr().out
    assert '"deltas"' in out2
