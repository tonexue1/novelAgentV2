"""ViolationLog 生命周期：内存追终态，日志只 append 一次。"""

from story_engine.nodes.system.violation_log import ViolationTracker, worst_severity
from story_engine.nodes.validation.hard_check import make_violation
from story_engine.primitives.enums import Severity
from story_engine.schemas.stores.violation import Locus, Violation
from story_engine.stores.json_backend import JsonStore


def _vio(msg: str = "越级", severity: Severity = Severity.CORRECT) -> Violation:
    return make_violation(
        rule="ability_monotonic",
        category="ability",
        severity=severity,
        message=msg,
        chapter=3,
        locus=Locus(chapter="c3", scene="c3.s1", beat="c3.s1.b2"),
    )


def _log(tmp_path):
    return JsonStore(Violation, tmp_path / "vio.jsonl", key_field="id")


def test_retry_updates_in_memory_and_appends_once(tmp_path):
    log = _log(tmp_path)
    tracker = ViolationTracker(log)
    v = tracker.track([_vio()])[0]

    tracker.note_attempt(level="beat", outcome="retry")
    tracker.note_attempt(level="scene", outcome="retry")
    assert len(log) == 0  # 未定终态，不落日志

    tracker.settle("fixed")
    assert len(log) == 1
    logged = log.get(v.id)
    assert logged is not None
    assert logged.resolution == "fixed"
    assert logged.retry_count == 2
    assert [h.level for h in logged.history] == ["beat", "scene"]
    assert logged.escalation_level == "scene"
    assert tracker.open_violations == []


def test_recheck_dedups_by_fingerprint(tmp_path):
    tracker = ViolationTracker(_log(tmp_path))
    first = tracker.track([_vio()])[0]
    again = tracker.track([_vio()])[0]  # 重检铸了新 id，但同一个问题
    assert again is first
    assert len(tracker) == 1


def test_blocked_flush(tmp_path):
    log = _log(tmp_path)
    tracker = ViolationTracker(log)
    tracker.track([_vio("挂起", Severity.BLOCK)])
    tracker.note_attempt(level="chapter", outcome="replan_failed")
    tracker.settle("blocked")
    assert [v.resolution for v in log.all()] == ["blocked"]


def test_worst_severity():
    assert worst_severity([]) is None
    assert worst_severity([_vio(severity=Severity.ADVISORY)]) == Severity.ADVISORY
    mixed = [_vio("a", Severity.ADVISORY), _vio("b", Severity.BLOCK), _vio("c", Severity.CORRECT)]
    assert worst_severity(mixed) == Severity.BLOCK
