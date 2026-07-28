"""M4a：WorldOp / TierNom / Summarizer / SummaryStore 幂等 / Retriever 分桶。"""

from story_engine.llm.base import LLMClient
from story_engine.nodes.base import NodeContext
from story_engine.nodes.system.applier import Applier
from story_engine.nodes.system.retriever import Query, retrieve
from story_engine.nodes.recorder.summarizer import SUMMARIZER_VERSION, Summarizer
from story_engine.primitives.enums import CharTier, WorldTier
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.artifacts.recorder_output import (
    MemOp,
    RecorderOutput,
    TierNom,
    WorldOp,
)
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.summary import SummaryDelta, SummaryEntry
from story_engine.schemas.stores.world import WorldEntity
from story_engine.stores.json_backend import JsonStore
from tests.factories import make_beat, make_chapter_script, make_scene
from tests.fake_llm import ScriptedProvider


def _stores(tmp_path):
    return {
        "mem": JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id"),
        "arc": JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id"),
        "world": JsonStore(WorldEntity, tmp_path / "w.jsonl", key_field="id"),
        "summary": JsonStore(SummaryEntry, tmp_path / "s.jsonl", key_field="key"),
    }


def test_world_op_register_and_update_state(tmp_path):
    s = _stores(tmp_path)
    ap = Applier()
    ro = RecorderOutput(
        chapter=3,
        world_ops=[
            WorldOp(
                entity_id="loc.shi_cun",
                op="REGISTER",
                canonical_name="石村",
                definition="叶凡故乡",
                evidence=[EvidenceSpan(chapter=3, scene=1, beats=(1, 1))],
            ),
            WorldOp(
                entity_id="loc.shi_cun",
                op="UPDATE_STATE",
                state={"ruler": "外族"},
                evidence=[EvidenceSpan(chapter=3, scene=1, beats=(2, 2))],
            ),
        ],
    )
    r = ap.apply_recorder_output(ro, s["mem"], s["arc"], world_store=s["world"])
    assert "loc.shi_cun" in r.world_ops_applied
    ent = s["world"].get("loc.shi_cun")
    assert ent is not None
    assert ent.origin == "emergent"
    assert ent.tier == WorldTier.MINOR
    assert ent.kind == "location"
    assert ent.state.get("ruler") == "外族"
    assert ent.visible_as_of(3)


def test_world_op_soft_invalidate(tmp_path):
    s = _stores(tmp_path)
    s["world"].append(WorldEntity(
        id="org.bandits", canonical_name="匪帮", origin="emergent", established_ch=1, t_valid=1,
    ))
    ap = Applier()
    ap.apply_recorder_output(
        RecorderOutput(chapter=5, world_ops=[
            WorldOp(entity_id="org.bandits", op="SOFT-INVALIDATE",
                    evidence=[EvidenceSpan(chapter=5)]),
        ]),
        s["mem"], s["arc"], world_store=s["world"],
    )
    assert s["world"].get("org.bandits").t_invalid == 5
    assert "org.bandits" not in {w.id for w in s["world"].as_of(5)}


def test_world_op_kind_literal_rejects_character():
    """WorldOp.kind 与 WorldEntity 同枚举；character 不得进结构化输出。"""
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        WorldOp(
            entity_id="char.ye_fan",
            op="REGISTER",
            kind="character",  # type: ignore[arg-type]
            evidence=[EvidenceSpan(chapter=3)],
        )


def test_world_op_register_bad_prefix_noop(tmp_path):
    """char.* 等非 world 前缀：Applier 降级 NOOP，不炸章。"""
    s = _stores(tmp_path)
    ap = Applier()
    r = ap.apply_recorder_output(
        RecorderOutput(
            chapter=3,
            world_ops=[
                WorldOp(
                    entity_id="char.ye_fan",
                    op="REGISTER",
                    canonical_name="叶凡",
                    evidence=[EvidenceSpan(chapter=3)],
                ),
                WorldOp(
                    entity_id="loc.shi_cun",
                    op="REGISTER",
                    canonical_name="石村",
                    evidence=[EvidenceSpan(chapter=3)],
                ),
            ],
        ),
        s["mem"],
        s["arc"],
        world_store=s["world"],
    )
    assert any(x.startswith("invalid_world_kind:char.ye_fan") for x in r.noops)
    assert "loc.shi_cun" in r.world_ops_applied
    assert s["world"].get("char.ye_fan") is None
    assert s["world"].get("loc.shi_cun") is not None


def test_world_op_kind_prefix_mismatch_noop(tmp_path):
    s = _stores(tmp_path)
    ap = Applier()
    r = ap.apply_recorder_output(
        RecorderOutput(
            chapter=3,
            world_ops=[
                WorldOp(
                    entity_id="loc.shi_cun",
                    op="REGISTER",
                    kind="item",
                    evidence=[EvidenceSpan(chapter=3)],
                ),
            ],
        ),
        s["mem"],
        s["arc"],
        world_store=s["world"],
    )
    assert any("invalid_world_kind:loc.shi_cun" in x for x in r.noops)
    assert s["world"].get("loc.shi_cun") is None


def test_tier_nom_apply(tmp_path):
    s = _stores(tmp_path)
    s["mem"].append(MemoryEntry(
        id="m.1", type="trait", scope="char.long_tao", text="龙套",
        t_valid=1, tier=CharTier.T3,
    ))
    ap = Applier()
    r = ap.apply_recorder_output(
        RecorderOutput(chapter=10, tier_noms=[
            TierNom(char="char.long_tao", from_tier=3, to_tier=1, reason="戏份加重",
                    evidence=[EvidenceSpan(chapter=10)]),
        ]),
        s["mem"], s["arc"], apply_tier_noms=True,
    )
    assert "char.long_tao" in r.tier_noms_applied
    assert s["mem"].get("m.1").tier == CharTier.T1


def test_tier_nom_deferred_by_default(tmp_path):
    s = _stores(tmp_path)
    s["mem"].append(MemoryEntry(
        id="m.1", type="trait", scope="char.x", text="t", t_valid=1, tier=CharTier.T3,
    ))
    r = Applier().apply_recorder_output(
        RecorderOutput(chapter=2, tier_noms=[
            TierNom(char="char.x", from_tier=3, to_tier=1, reason="x",
                    evidence=[EvidenceSpan(chapter=2)]),
        ]),
        s["mem"], s["arc"],
    )
    assert any(n.startswith("tier_nom:") for n in r.noops)
    assert s["mem"].get("m.1").tier == CharTier.T3


def test_summary_delta_idempotent_upsert(tmp_path):
    s = _stores(tmp_path)
    ap = Applier()
    e1 = SummaryEntry(level="chapter", ref="c1", text="初版", t_valid=1, summarizer_version="v1")
    ap.apply_summary_delta(SummaryDelta(chapter=1, entries=[e1]), s["summary"])
    assert s["summary"].get("chapter:c1").text == "初版"

    e2 = SummaryEntry(level="chapter", ref="c1", text="修订版", t_valid=1, summarizer_version="v2")
    ap.apply_summary_delta(SummaryDelta(chapter=1, entries=[e2]), s["summary"])
    assert len(s["summary"]) == 1
    assert s["summary"].get("chapter:c1").text == "修订版"
    assert s["summary"].get("chapter:c1").summarizer_version == "v2"


def test_summarizer_produces_scene_and_chapter(tmp_path):
    script = make_chapter_script(
        "c1",
        [make_scene("c1.s1", [make_beat("c1.s1.b1", "叩门"), make_beat("c1.s1.b2", "受试")])],
    )
    ctx = NodeContext(llm=LLMClient(ScriptedProvider()))
    delta = Summarizer().summarize(ctx, chapter=1, script=script)
    levels = {e.level for e in delta.entries}
    assert "scene" in levels and "chapter" in levels
    assert all(e.summarizer_version == SUMMARIZER_VERSION for e in delta.entries)
    assert any(e.ref == "c1" for e in delta.entries)


def test_retriever_fact_in_character_bucket(tmp_path):
    s = _stores(tmp_path)
    s["mem"].append(MemoryEntry(
        id="m.fact", type="fact", scope="char.x", text="发生过的事", t_valid=3, salience=0.6,
    ))
    s["mem"].append(MemoryEntry(
        id="m.trait", type="trait", scope="char.x", text="沉稳", t_valid=1, salience=0.6,
    ))
    s["summary"].append(SummaryEntry(
        level="chapter", ref="c1", text="过去章摘要很长很长很长", t_valid=1,
    ))
    res = retrieve(
        Query(as_of_chapter=5, char="char.x", budget_tokens=4000),
        s["mem"], s["arc"], summary_store=s["summary"],
    )
    by = {it.item_id: it.bucket for it in res.items}
    assert by["m.fact"] == "character"
    assert by["m.trait"] == "character"
    assert by["chapter:c1"] == "streaming"


def test_retriever_streaming_excludes_current_chapter_summary(tmp_path):
    s = _stores(tmp_path)
    s["summary"].append(SummaryEntry(level="chapter", ref="c5", text="本章摘要", t_valid=5))
    s["summary"].append(SummaryEntry(level="chapter", ref="c4", text="上章摘要", t_valid=4))
    s["mem"].append(MemoryEntry(
        id="m1", type="goal", scope="char.x", text="目标", t_valid=1, salience=0.9,
    ))
    res = retrieve(
        Query(as_of_chapter=5, char="char.x", budget_tokens=4000),
        s["mem"], summary_store=s["summary"],
    )
    ids = set(res.item_ids)
    assert "chapter:c4" in ids
    assert "chapter:c5" not in ids
