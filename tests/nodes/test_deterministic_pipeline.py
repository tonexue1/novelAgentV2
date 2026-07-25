"""M1 确定性半边集成 smoke：commit → apply → hard-check → retrieve。

证明非 LLM 骨架能端到端组合（LLM 半边留 M2）。
"""

from story_engine.nodes.system.applier import Applier
from story_engine.nodes.system.retriever import Query, retrieve
from story_engine.nodes.validation.hard_check import check_evidence_resolvable
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.artifacts.recorder_output import MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene
from story_engine.stores.json_backend import JsonStore


def test_deterministic_half_composes(tmp_path):
    script_store: JsonStore[ChapterScript] = JsonStore(
        ChapterScript, tmp_path / "script.jsonl", key_field="chapter"
    )
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="arc_id")
    ap = Applier()

    # 1) beat 定序 + 提交 ScriptStore（主真相）
    script = ChapterScript(
        chapter="c1",
        scenes=[Scene(scene_id="c1.s1", beats=[
            Beat(beat_id="tmp", content="叶凡拜入青云门"),
            Beat(beat_id="tmp", content="立誓为父报仇"),
        ])],
    )
    ap.assign_beat_ids(script)
    script_store.append(script)

    # 2) 应用抽取增量（evidence 回指已提交位置）
    ro = RecorderOutput(
        chapter=1,
        mem_ops=[
            MemOp(op="ADD", scope="char:ye_fan", type="fact", text="拜入青云门",
                  evidence=[EvidenceSpan.parse("c1.s1.b1")]),
            MemOp(op="ADD", scope="char:ye_fan", type="goal", text="为父报仇",
                  evidence=[EvidenceSpan.parse("c1.s1.b2")]),
        ],
    )
    ap.apply_recorder_output(ro, mem, arc)
    assert len(mem) == 2

    # 3) Hard-Check：evidence 全部可解析 → 无 BLOCK
    vios = check_evidence_resolvable(mem.all(), script_store, chapter=1)
    assert vios == []

    # 4) Retriever：as-of 第 3 章检回该角色记忆
    res = retrieve(Query(as_of_chapter=3, char_id="ye_fan", focus="报仇", budget_tokens=4000), mem, arc)
    assert len(res.items) == 2
