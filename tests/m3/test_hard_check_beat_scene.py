"""逐拍即时硬检 + 场级硬检的规则清单。"""

from story_engine.nodes.validation.hard_check import (
    build_ability_ladder,
    check_beat,
    check_scene,
    ids_in_text,
)
from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import StoryTime
from story_engine.schemas.artifacts.scene_script import (
    ContractCast,
    Obligation,
    ObligationBinding,
    SceneContract,
)
from story_engine.schemas.stores.arc import ArcRecord, Knowledge
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.stores.json_backend import JsonStore
from tests.factories import make_beat, make_scene


def _contract(**kw) -> SceneContract:
    base = dict(
        scene_id="c3.s1",
        location="loc.qing_yun",
        pov="char.ye_fan",
        goal="拿到剑",
        conflict="守卫拦路",
        cast=[ContractCast(char="char.ye_fan", entry_state="紧张")],
        obligations=[Obligation(obligation_id="c3.s1.o1", desc="逼守卫让路")],
    )
    base.update(kw)
    return SceneContract(**base)


def _arc_store(tmp_path, *records):
    s: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "arc.jsonl", key_field="id")
    for r in records:
        s.append(r)
    return s


def _mem_store(tmp_path, *entries):
    s: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    for e in entries:
        s.append(e)
    return s


# ── 逐拍 ────────────────────────────────────────────────────
def test_owner_not_in_cast_blocks():
    beat = make_beat("c3.s1.b1", owner="char.ghost")
    vios = check_beat(beat, contract=_contract(), chapter=3)
    assert [v.category for v in vios] == ["alive_present"]
    assert vios[0].severity == Severity.BLOCK
    assert vios[0].locus.beat == "c3.s1.b1"
    assert vios[0].stage == "director·dispatch"


def test_hits_must_point_to_real_obligation():
    beat = make_beat("c3.s1.b1", hits="c3.s1.o9")
    vios = check_beat(beat, contract=_contract(), chapter=3)
    assert [v.category for v in vios] == ["ref_integrity"]
    assert vios[0].severity == Severity.CORRECT


def test_prose_ref_integrity_and_secret_boundary(tmp_path):
    arc = _arc_store(
        tmp_path,
        ArcRecord(id="sec.blood", kind="secret", state="PLANTED", desc="血脉",
                  knowledge=[Knowledge(char="char.pang_bo", since_ch=1)]),
    )
    beat = make_beat("c3.s1.b1", text="他提起 sec.blood 与 fs.missing", kind="dialogue")
    vios = check_beat(beat, contract=_contract(), chapter=3, arc_store=arc)
    cats = sorted(v.category for v in vios)
    assert cats == ["POV", "ref_integrity"]  # fs.missing 不在册 + 叶凡不知情
    assert any("fs.missing" in v.message for v in vios)


def test_clean_beat_has_no_violation(tmp_path):
    arc = _arc_store(tmp_path)
    beat = make_beat("c3.s1.b1", text="他握紧了拳头", hits="c3.s1.o1")
    assert check_beat(beat, contract=_contract(), chapter=3, arc_store=arc) == []


def test_ability_ceiling(tmp_path):
    mem = _mem_store(
        tmp_path,
        MemoryEntry(id="m.1", type="ability", scope="char.ye_fan", text="炼气",
                    t_valid=1, ability_rank=1),
        MemoryEntry(id="m.2", type="ability", scope="char.pang_bo", text="金丹",
                    t_valid=1, ability_rank=5),
    )
    assert build_ability_ladder(mem) == {"炼气": 1, "金丹": 5}
    beat = make_beat("c3.s1.b1", text="他一步踏入金丹之境")
    vios = check_beat(beat, contract=_contract(), chapter=3, mem_store=mem)
    assert len(vios) == 1
    assert vios[0].category == "ability" and vios[0].severity == Severity.BLOCK


def test_ability_ceiling_silent_without_ladder(tmp_path):
    mem = _mem_store(tmp_path)  # 没有带 rank 的 ability 记忆 → 规则不跑
    beat = make_beat("c3.s1.b1", text="他一步踏入金丹之境")
    assert check_beat(beat, contract=_contract(), chapter=3, mem_store=mem) == []


def test_ids_in_text():
    assert ids_in_text("看到 loc.qing_yun 和 fs.sword，还有 char.x") == ["loc.qing_yun", "fs.sword"]


# ── 场级 ────────────────────────────────────────────────────
def test_scene_pov_and_location(tmp_path):
    scene = make_scene("c3.s1", [make_beat("c3.s1.b1", hits="c3.s1.o1")], location="loc.unknown")
    vios = check_scene(
        scene, contract=_contract(), chapter=3, world_ids={"loc.qing_yun"}
    )
    cats = sorted(v.category for v in vios)
    assert cats == ["POV", "location"]  # cast 为空 → POV 不在场；地点不在册
    loc_vio = next(v for v in vios if v.category == "location")
    assert loc_vio.severity == Severity.ADVISORY
    assert all(v.escalation_level == "scene" for v in vios)


def test_fulfill_before_plant(tmp_path):
    arc = _arc_store(
        tmp_path,
        ArcRecord(id="fs.sword", kind="foreshadow", state="PLANNED", desc="断剑"),
    )
    contract = _contract(
        obligations=[
            Obligation(
                obligation_id="c3.s1.o1",
                desc="收断剑",
                binds=ObligationBinding(op="FULFILL", fs_id="fs.sword"),
            )
        ]
    )
    scene = make_scene(
        "c3.s1", [make_beat("c3.s1.b1", hits="c3.s1.o1")], pov="char.ye_fan"
    )
    scene.cast = []
    vios = [v for v in check_scene(scene, contract=contract, chapter=3, arc_store=arc)
            if v.category == "foreshadow_order"]
    assert len(vios) == 1
    assert vios[0].locus.obligation == "c3.s1.o1"
    assert vios[0].severity == Severity.CORRECT


def test_timeline_no_backflow():
    prev = make_scene("c3.s1")
    prev.time = StoryTime(day=5)
    cur = make_scene("c3.s2", [make_beat("c3.s2.b1", hits="c3.s1.o1")])
    cur.time = StoryTime(day=3)
    vios = [v for v in check_scene(cur, contract=_contract(), chapter=3, previous_scenes=[prev])
            if v.category == "timeline"]
    assert len(vios) == 1 and vios[0].severity == Severity.BLOCK


def test_missed_obligations_advisory():
    scene = make_scene("c3.s1", [make_beat("c3.s1.b1")])
    vios = [v for v in check_scene(scene, contract=_contract(), chapter=3)
            if v.category == "logic"]
    assert len(vios) == 1 and vios[0].severity == Severity.ADVISORY
    assert vios[0].refs == ["c3.s1.o1"]
