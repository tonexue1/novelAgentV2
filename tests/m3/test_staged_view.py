"""StagedScriptView：未落库章可被 span 解析，落库前真 store 查不到。"""

import pytest

from story_engine.nodes.validation.hard_check import resolve_span
from story_engine.orchestrator.staged import StagedScriptView
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.stores.script import ChapterScript
from story_engine.stores.json_backend import JsonStore
from tests.factories import make_beat, make_chapter_script, make_scene


def _store(tmp_path):
    return JsonStore(ChapterScript, tmp_path / "script.jsonl", key_field="chapter")


def _view(tmp_path):
    store = _store(tmp_path)
    store.append(make_chapter_script("c1", [make_scene("c1.s1", [make_beat()])]))
    return store, StagedScriptView(store, make_chapter_script("c2", []))


def test_staged_span_resolvable_before_commit(tmp_path):
    store, view = _view(tmp_path)
    view.open_scene(make_scene("c2.s1"))
    view.stage_beat(make_beat())
    view.stage_beat(make_beat())

    assert resolve_span(EvidenceSpan.parse("c2.s1.b2"), view)
    assert not resolve_span(EvidenceSpan.parse("c2.s1.b3"), view)
    assert not resolve_span(EvidenceSpan.parse("c2"), store)  # 真 store 还没有这章
    assert resolve_span(EvidenceSpan.parse("c1.s1.b1"), view)  # 已落库章仍走 store


def test_stage_beat_mints_ids(tmp_path):
    _, view = _view(tmp_path)
    view.open_scene(make_scene("c2.s1"))
    b1 = view.stage_beat(make_beat())
    b2 = view.stage_beat(make_beat())
    assert [b1.beat_id, b2.beat_id] == ["c2.s1.b1", "c2.s1.b2"]


def test_drop_last_beat_then_restage(tmp_path):
    _, view = _view(tmp_path)
    view.open_scene(make_scene("c2.s1"))
    view.stage_beat(make_beat(text="旧"))
    view.stage_beat(make_beat(text="坏"))
    dropped = view.drop_last_beat()
    assert dropped.action.stage == "坏"
    again = view.stage_beat(make_beat(text="好"))
    assert again.beat_id == "c2.s1.b2"
    assert len(view.draft_scene.beats) == 2


def test_admit_and_commit(tmp_path):
    store, view = _view(tmp_path)
    view.open_scene(make_scene("c2.s1"))
    view.stage_beat(make_beat())
    view.admit_scene()
    assert view.draft_scene is None
    assert store.get("c2") is None  # 还没落库

    script = view.commit(consistency_status="clean")
    assert script.consistency_status == "clean"
    assert store.get("c2") is not None
    assert len(store.get("c2").scenes) == 1


def test_commit_refuses_open_draft(tmp_path):
    _, view = _view(tmp_path)
    view.open_scene(make_scene("c2.s1"))
    with pytest.raises(RuntimeError):
        view.commit(consistency_status="clean")
