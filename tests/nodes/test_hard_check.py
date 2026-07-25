"""Hard-Check 确定性 UT：evidence 可解析 / 修为单调 / secret 边界。"""

from story_engine.nodes.validation.hard_check import (
    check_ability_monotonic,
    check_evidence_resolvable,
    check_secret_boundary,
    resolve_span,
)
from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene
from story_engine.stores.json_backend import JsonStore


def _script_store(tmp_path):
    s: JsonStore[ChapterScript] = JsonStore(ChapterScript, tmp_path / "script.jsonl", key_field="chapter")
    s.append(
        ChapterScript(
            chapter="c12",
            scenes=[
                Scene(
                    scene_id="c12.s3",
                    beats=[
                        Beat(beat_id="c12.s3.b1", content="a"),
                        Beat(beat_id="c12.s3.b2", content="b"),
                    ],
                )
            ],
        )
    )
    return s


def test_resolve_span(tmp_path):
    ss = _script_store(tmp_path)
    assert resolve_span(EvidenceSpan.parse("c12"), ss)
    assert resolve_span(EvidenceSpan.parse("c12.s3"), ss)
    assert resolve_span(EvidenceSpan.parse("c12.s3.b2"), ss)
    assert not resolve_span(EvidenceSpan.parse("c12.s3.b5"), ss)  # beat 越界
    assert not resolve_span(EvidenceSpan.parse("c99"), ss)         # 章不存在


def test_evidence_unresolvable_blocks(tmp_path):
    ss = _script_store(tmp_path)
    mem = MemoryEntry(mem_id="m.x", scope="char:x", type="fact", text="t",
                      t_valid=12, evidence=[EvidenceSpan.parse("c12.s3.b9")])
    vios = check_evidence_resolvable([mem], ss, chapter=12)
    assert len(vios) == 1
    assert vios[0].severity == Severity.BLOCK
    assert vios[0].rule == "evidence_resolvable"


def test_ability_monotonic_violation(tmp_path):
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id")
    mem.append(MemoryEntry(mem_id="m.1", scope="char:x", type="ability", text="炼气", t_valid=3, ability_rank=2))
    mem.append(MemoryEntry(mem_id="m.2", scope="char:x", type="ability", text="金丹", t_valid=10, ability_rank=5))
    mem.append(MemoryEntry(mem_id="m.3", scope="char:x", type="ability", text="退回炼气", t_valid=20, ability_rank=2))
    vios = check_ability_monotonic(mem, "char:x", chapter=20)
    assert len(vios) == 1
    assert vios[0].severity == Severity.BLOCK
    assert "倒退" in vios[0].detail


def test_ability_monotonic_ok(tmp_path):
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id")
    mem.append(MemoryEntry(mem_id="m.1", scope="char:x", type="ability", text="炼气", t_valid=3, ability_rank=2))
    mem.append(MemoryEntry(mem_id="m.2", scope="char:x", type="ability", text="金丹", t_valid=10, ability_rank=5))
    assert check_ability_monotonic(mem, "char:x", chapter=10) == []


def test_secret_boundary(tmp_path):
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "arc.jsonl", key_field="arc_id")
    arc.append(ArcRecord(arc_id="sec.blood", kind="secret", status="PLANTED",
                         desc="魔族血脉", hidden_from=["ye_fan"]))
    vios = check_secret_boundary("ye_fan", ["sec.blood"], arc, chapter=15)
    assert len(vios) == 1 and vios[0].severity == Severity.CORRECT
    # 知情者不触发
    assert check_secret_boundary("pang_bo", ["sec.blood"], arc, chapter=15) == []
