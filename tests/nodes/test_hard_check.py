"""Hard-Check 确定性 UT：evidence 可解析 / 修为单调(as-of) / secret 边界(knowledge[])。"""

from story_engine.nodes.validation.hard_check import (
    check_ability_monotonic,
    check_evidence_resolvable,
    check_secret_boundary,
    resolve_span,
)
from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.stores.arc import ArcRecord, Knowledge
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


def _mem_store(tmp_path):
    return JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")


def test_resolve_span(tmp_path):
    ss = _script_store(tmp_path)
    assert resolve_span(EvidenceSpan.parse("c12"), ss)
    assert resolve_span(EvidenceSpan.parse("c12.s3"), ss)
    assert resolve_span(EvidenceSpan.parse("c12.s3.b2"), ss)
    assert not resolve_span(EvidenceSpan.parse("c12.s3.b5"), ss)  # beat 越上界
    assert not resolve_span(EvidenceSpan.parse("c99"), ss)         # 章不存在


def test_evidence_unresolvable_blocks(tmp_path):
    ss = _script_store(tmp_path)
    mem = MemoryEntry(id="m.x", scope="char.x", type="fact", text="t",
                      t_valid=12, evidence=[EvidenceSpan.parse("c12.s3.b9")])
    vios = check_evidence_resolvable([mem], ss, chapter=12)
    assert len(vios) == 1
    assert vios[0].severity == Severity.BLOCK
    assert vios[0].rule == "evidence_resolvable"


def test_ability_monotonic_violation(tmp_path):
    mem = _mem_store(tmp_path)
    mem.append(MemoryEntry(id="m.1", scope="char.x", type="ability", text="炼气", t_valid=3, ability_rank=2))
    mem.append(MemoryEntry(id="m.2", scope="char.x", type="ability", text="金丹", t_valid=10, ability_rank=5))
    mem.append(MemoryEntry(id="m.3", scope="char.x", type="ability", text="退回炼气", t_valid=20, ability_rank=2))
    vios = check_ability_monotonic(mem, "char.x", chapter=20)
    assert len(vios) == 1
    assert vios[0].severity == Severity.BLOCK
    assert "倒退" in vios[0].detail


def test_ability_monotonic_ok(tmp_path):
    mem = _mem_store(tmp_path)
    mem.append(MemoryEntry(id="m.1", scope="char.x", type="ability", text="炼气", t_valid=3, ability_rank=2))
    mem.append(MemoryEntry(id="m.2", scope="char.x", type="ability", text="金丹", t_valid=10, ability_rank=5))
    assert check_ability_monotonic(mem, "char.x", chapter=10) == []


def test_ability_monotonic_asof_excludes_future(tmp_path):
    """as-of：未来章的倒退台阶在早章检查时不参检。"""
    mem = _mem_store(tmp_path)
    mem.append(MemoryEntry(id="m.1", scope="char.x", type="ability", text="炼气", t_valid=3, ability_rank=2))
    mem.append(MemoryEntry(id="m.2", scope="char.x", type="ability", text="金丹", t_valid=10, ability_rank=5))
    mem.append(MemoryEntry(id="m.3", scope="char.x", type="ability", text="未来倒退", t_valid=20, ability_rank=2))
    # 在第 12 章检查时看不到第 20 章的倒退
    assert check_ability_monotonic(mem, "char.x", chapter=12) == []


def test_secret_boundary(tmp_path):
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "arc.jsonl", key_field="id")
    arc.append(ArcRecord(id="sec.blood", kind="secret", state="PLANTED", desc="魔族血脉",
                         knowledge=[Knowledge(char="char.pang_bo", since_ch=1)]))
    # ye_fan 不在知情名单 → 认知边界穿帮
    vios = check_secret_boundary("char.ye_fan", ["sec.blood"], arc, chapter=15)
    assert len(vios) == 1 and vios[0].severity == Severity.CORRECT
    # 知情者不触发
    assert check_secret_boundary("char.pang_bo", ["sec.blood"], arc, chapter=15) == []


def test_secret_boundary_asof(tmp_path):
    """as-of：知情发生前引用即穿帮，知情后不穿帮。"""
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "arc.jsonl", key_field="id")
    arc.append(ArcRecord(id="sec.s", kind="secret", state="PLANTED", desc="身世",
                         knowledge=[Knowledge(char="char.ye_fan", since_ch=10)]))
    assert len(check_secret_boundary("char.ye_fan", ["sec.s"], arc, chapter=5)) == 1   # 尚未知情
    assert check_secret_boundary("char.ye_fan", ["sec.s"], arc, chapter=10) == []      # 恰好知情
