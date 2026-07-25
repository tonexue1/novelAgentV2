"""Applier 确定性 UT：beat 定序 / MemOp 软失效 / ArcOp 状态机。"""

from story_engine.nodes.system.applier import Applier
from story_engine.schemas.artifacts.recorder_output import ArcOp, MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene
from story_engine.stores.json_backend import JsonStore


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
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="arc_id")
    ap = Applier()

    r1 = ap.apply_recorder_output(
        RecorderOutput(chapter=3, mem_ops=[MemOp(op="ADD", scope="char:x", type="fact", text="拜师")]),
        mem, arc,
    )
    assert len(r1.added_mem) == 1
    new_id = r1.added_mem[0]
    assert mem.get(new_id).t_valid == 3

    # 第 10 章软失效
    r2 = ap.apply_recorder_output(
        RecorderOutput(chapter=10, mem_ops=[MemOp(op="INVALIDATE", target_mem_id=new_id)]),
        mem, arc,
    )
    assert r2.invalidated_mem == [new_id]
    # as-of：第 5 章可见，第 10 章起不可见
    assert new_id in {m.mem_id for m in mem.as_of(5)}
    assert new_id not in {m.mem_id for m in mem.as_of(10)}


def test_apply_arc_state_machine(tmp_path):
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="arc_id")
    ap = Applier()

    ap.apply_recorder_output(
        RecorderOutput(chapter=1, arc_ops=[ArcOp(op="PLANT", arc_id="fs.jade", desc="玉佩")]),
        mem, arc,
    )
    assert arc.get("fs.jade").status == "PLANTED"

    ap.apply_recorder_output(
        RecorderOutput(chapter=8, arc_ops=[ArcOp(op="FULFILL", arc_id="fs.jade")]),
        mem, arc,
    )
    assert arc.get("fs.jade").status == "FULFILLED"


def test_persistence_after_invalidate(tmp_path):
    """软失效后重新加载 store，t_invalid 应持久化。"""
    path = tmp_path / "m.jsonl"
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, path, key_field="mem_id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="arc_id")
    ap = Applier()
    nid = ap.apply_recorder_output(
        RecorderOutput(chapter=1, mem_ops=[MemOp(op="ADD", scope="char:x", type="fact", text="t")]),
        mem, arc,
    ).added_mem[0]
    ap.apply_recorder_output(
        RecorderOutput(chapter=9, mem_ops=[MemOp(op="INVALIDATE", target_mem_id=nid)]), mem, arc
    )
    reloaded: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, path, key_field="mem_id")
    assert reloaded.get(nid).t_invalid == 9
