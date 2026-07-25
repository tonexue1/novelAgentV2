"""Applier 确定性 UT：beat 定序 / MemOp / ArcOp 状态机（对齐冻结 schema）。"""

import pytest

from story_engine.nodes.system.applier import Applier
from story_engine.schemas.artifacts.recorder_output import ArcOp, MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene
from story_engine.stores.json_backend import JsonStore


def _stores(tmp_path):
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    return mem, arc


def test_assign_beat_ids():
    script = ChapterScript(
        chapter="c5",
        scenes=[
            Scene(scene_id="c5.s1", beats=[Beat(beat_id="tmp", content="a"), Beat(beat_id="tmp", content="b")]),
            Scene(scene_id="c5.s2", beats=[Beat(beat_id="tmp", content="c")]),
        ],
    )
    Applier().assign_beat_ids(script)
    assert [b.beat_id for b in script.scenes[0].beats] == ["c5.s1.b1", "c5.s1.b2"]
    assert script.scenes[1].beats[0].beat_id == "c5.s2.b1"


def test_apply_mem_add_and_invalidate(tmp_path):
    mem, arc = _stores(tmp_path)
    ap = Applier()

    r1 = ap.apply_recorder_output(
        RecorderOutput(chapter=3, mem_ops=[MemOp(action="ADD", scope="char.x", type="fact", text="拜师")]),
        mem, arc,
    )
    assert len(r1.added_mem) == 1
    new_id = r1.added_mem[0]
    assert mem.get(new_id).t_valid == 3
    assert mem.get(new_id).scope == "char.x"

    r2 = ap.apply_recorder_output(
        RecorderOutput(chapter=10, mem_ops=[MemOp(action="SOFT-INVALIDATE", target_id=new_id, resolution="superseded")]),
        mem, arc,
    )
    assert r2.invalidated_mem == [new_id]
    assert mem.get(new_id).resolution.value == "superseded"
    # as-of：第 5 章可见，第 10 章起不可见
    assert new_id in {m.id for m in mem.as_of(5)}
    assert new_id not in {m.id for m in mem.as_of(10)}


def test_apply_mem_reinforce(tmp_path):
    mem, arc = _stores(tmp_path)
    ap = Applier()
    nid = ap.apply_recorder_output(
        RecorderOutput(chapter=1, mem_ops=[MemOp(action="ADD", scope="char.x", type="belief", text="信念", strength=0.4)]),
        mem, arc,
    ).added_mem[0]

    r = ap.apply_recorder_output(
        RecorderOutput(chapter=4, mem_ops=[MemOp(action="REINFORCE", target_id=nid, strength=0.8)]),
        mem, arc,
    )
    assert r.reinforced_mem == [nid]
    assert mem.get(nid).strength == 0.8


def test_apply_mem_noop_logged(tmp_path):
    mem, arc = _stores(tmp_path)
    r = Applier().apply_recorder_output(
        RecorderOutput(chapter=1, mem_ops=[MemOp(action="NOOP")]), mem, arc
    )
    assert len(r.noops) == 1


def test_apply_arc_state_machine(tmp_path):
    mem, arc = _stores(tmp_path)
    ap = Applier()
    # 台账已有 PLANNED（创世 init）
    arc.append(ArcRecord(id="fs.jade", kind="foreshadow", desc="玉佩", state="PLANNED"))

    ap.apply_recorder_output(
        RecorderOutput(chapter=1, arc_ops=[ArcOp(target_id="fs.jade", op="PLANT")]), mem, arc,
    )
    rec = arc.get("fs.jade")
    assert rec.state == "PLANTED"
    assert [h.transition for h in rec.history] == ["PLANT"]

    ap.apply_recorder_output(
        RecorderOutput(chapter=8, arc_ops=[ArcOp(target_id="fs.jade", op="FULFILL")]), mem, arc,
    )
    rec = arc.get("fs.jade")
    assert rec.state == "FULFILLED"
    assert [h.transition for h in rec.history] == ["PLANT", "FULFILL"]


def test_arc_illegal_transition_fulfill_before_plant(tmp_path):
    """FULFILL 一个还是 PLANNED（未 PLANT）的伏笔 → 守卫拒绝。"""
    mem, arc = _stores(tmp_path)
    arc.append(ArcRecord(id="fs.x", kind="foreshadow", desc="x", state="PLANNED"))
    with pytest.raises(ValueError):
        Applier().apply_recorder_output(
            RecorderOutput(chapter=2, arc_ops=[ArcOp(target_id="fs.x", op="FULFILL")]), mem, arc,
        )


def test_arc_terminal_protection(tmp_path):
    """终态 FULFILLED 不可再被改动。"""
    mem, arc = _stores(tmp_path)
    arc.append(ArcRecord(id="fs.x", kind="foreshadow", desc="x", state="FULFILLED"))
    with pytest.raises(ValueError):
        Applier().apply_recorder_output(
            RecorderOutput(chapter=2, arc_ops=[ArcOp(target_id="fs.x", op="REINFORCE")]), mem, arc,
        )


def test_arc_op_on_nonexistent_requires_is_new(tmp_path):
    mem, arc = _stores(tmp_path)
    with pytest.raises(ValueError):
        Applier().apply_recorder_output(
            RecorderOutput(chapter=1, arc_ops=[ArcOp(target_id="fs.ghost", op="PLANT")]), mem, arc,
        )


def test_arc_emergent_creation(tmp_path):
    """is_new + draft：涌现伏笔（皆字秘那种临时起意）就地建档并 PLANT。"""
    mem, arc = _stores(tmp_path)
    Applier().apply_recorder_output(
        RecorderOutput(chapter=30, arc_ops=[
            ArcOp(target_id="fs.jiezimi", op="PLANT", is_new=True,
                  draft={"desc": "皆字秘", "importance": "major"}),
        ]), mem, arc,
    )
    rec = arc.get("fs.jiezimi")
    assert rec.state == "PLANTED"
    assert rec.origin == "emergent"
    assert rec.established_ch == 30


def test_arc_secret_reveal(tmp_path):
    """REVEAL：as-of 知情名单增量。"""
    mem, arc = _stores(tmp_path)
    arc.append(ArcRecord(id="sec.s", kind="secret", desc="身世", state="PLANTED"))
    Applier().apply_recorder_output(
        RecorderOutput(chapter=12, arc_ops=[ArcOp(target_id="sec.s", kind="secret", op="REVEAL",
                                                  reveal_to=["char.ye_fan"])]),
        mem, arc,
    )
    rec = arc.get("sec.s")
    assert rec.knows_as_of("char.ye_fan", 12)
    assert not rec.knows_as_of("char.ye_fan", 11)


def test_arc_thread_progression(tmp_path):
    mem, arc = _stores(tmp_path)
    arc.append(ArcRecord(id="th.main", kind="thread", desc="主线", thread_state="OPEN", tier="main"))
    ap = Applier()
    ap.apply_recorder_output(
        RecorderOutput(chapter=2, arc_ops=[ArcOp(target_id="th.main", kind="thread", op="ADVANCE", milestone="踏出第一步")]),
        mem, arc,
    )
    rec = arc.get("th.main")
    assert rec.thread_state == "ADVANCING"
    assert rec.advances[0].milestone == "踏出第一步"


def test_persistence_after_invalidate(tmp_path):
    """软失效后重新加载 store，t_invalid 应持久化。"""
    path = tmp_path / "m.jsonl"
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, path, key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    ap = Applier()
    nid = ap.apply_recorder_output(
        RecorderOutput(chapter=1, mem_ops=[MemOp(action="ADD", scope="char.x", type="fact", text="t")]),
        mem, arc,
    ).added_mem[0]
    ap.apply_recorder_output(
        RecorderOutput(chapter=9, mem_ops=[MemOp(action="SOFT-INVALIDATE", target_id=nid)]), mem, arc
    )
    reloaded: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, path, key_field="id")
    assert reloaded.get(nid).t_invalid == 9
