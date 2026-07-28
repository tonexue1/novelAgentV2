"""M4b：Embedder / 语义召回 / Replanner / 伏笔逾期 / 卷边界。"""

from story_engine.llm.base import LLMClient
from story_engine.nodes.base import NodeContext
from story_engine.nodes.planning.replanner import compute_drift, decide_action
from story_engine.nodes.system.applier import Applier
from story_engine.nodes.system.embedder import FakeEmbedder, build_embedder, cosine
from story_engine.nodes.system.foreshadow import core_overdue, surface_foreshadows
from story_engine.nodes.system.retriever import Query, retrieve
from story_engine.orchestrator.loop import run_volume_review
from story_engine.primitives.enums import Importance
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.artifacts.recorder_output import MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L0, L1, L2, PayoffDeadline, Thread, Foreshadow, ChapterBeat
from story_engine.schemas.stores.summary import SummaryEntry
from story_engine.stores.json_backend import JsonStore
from tests.fake_llm import ScriptedProvider


def test_fake_embedder_deterministic():
    emb = FakeEmbedder(dim=32)
    a = emb.embed(["青云门拜师"])[0]
    b = emb.embed(["青云门拜师"])[0]
    c = emb.embed(["完全无关的西瓜"])[0]
    assert a == b
    assert abs(sum(x * x for x in a) - 1.0) < 1e-6
    assert cosine(a, b) > cosine(a, c)


def test_caching_embedder_via_factory():
    emb = build_embedder()  # fake + cache
    v1 = emb.embed(["同一句"])[0]
    v2 = emb.embed(["同一句"])[0]
    assert v1 == v2


def test_applier_writes_vec_on_mem_and_summary(tmp_path):
    emb = FakeEmbedder(dim=16)
    ap = Applier(embedder=emb)
    mem = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    summary = JsonStore(SummaryEntry, tmp_path / "s.jsonl", key_field="key")
    ap.apply_recorder_output(
        RecorderOutput(chapter=1, mem_ops=[
            MemOp(action="ADD", scope="char.x", type="fact", text="拜入青云门",
                  evidence=[EvidenceSpan(chapter=1)]),
        ]),
        mem, arc,
    )
    entry = mem.all()[0]
    assert entry.vec is not None and len(entry.vec) == 16

    from story_engine.schemas.stores.summary import SummaryDelta
    ap.apply_summary_delta(
        SummaryDelta(chapter=1, entries=[
            SummaryEntry(level="chapter", ref="c1", text="入门之日", t_valid=1),
        ]),
        summary,
    )
    assert summary.get("chapter:c1").vec is not None


def test_semantic_retrieval_prefers_similar(tmp_path):
    emb = FakeEmbedder(dim=64)
    mem = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    texts = [
        ("m.qing", "叶凡拜入青云门求道"),
        ("m.melon", "集市上卖西瓜的小贩"),
    ]
    for mid, text in texts:
        vec = emb.embed([text])[0]
        mem.append(MemoryEntry(
            id=mid, type="fact", scope="char.ye_fan", text=text,
            t_valid=1, salience=0.5, vec=vec,
        ))
    qvec = emb.embed(["青云门拜师"])[0]
    res = retrieve(
        Query(as_of_chapter=5, char="char.ye_fan", focus="", budget_tokens=4000, query_vec=qvec),
        mem,
    )
    assert res.item_ids[0] == "m.qing"


def test_foreshadow_due_and_core_overdue(tmp_path):
    arc = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    arc.append(ArcRecord(
        id="fs.minor", kind="foreshadow", desc="小伏笔", state="PLANTED",
        importance=Importance.MINOR,
        payoff_deadline=PayoffDeadline(granularity="chapter", ref="c10"),
    ))
    arc.append(ArcRecord(
        id="fs.core", kind="foreshadow", desc="身世", state="PLANTED",
        importance=Importance.CORE,
        payoff_deadline=PayoffDeadline(granularity="chapter", ref="c5"),
    ))
    # 第 5 章：core 逾期；minor 临期（窗口=2 → 8..9 due，10 overdue）
    sigs = surface_foreshadows(arc, 5)
    assert any(s.arc_id == "fs.core" and s.status == "overdue" for s in sigs)
    assert core_overdue(sigs)
    sigs9 = surface_foreshadows(arc, 9)
    assert any(s.arc_id == "fs.minor" and s.status == "due" for s in sigs9)


def test_decide_action_core_overdue_forces_revise():
    from story_engine.nodes.system.foreshadow import ForeshadowSignal
    from story_engine.nodes.planning.replanner import DriftReport

    drift = DriftReport(thread_lag=0, foreshadow_overdue_rate=0.1)
    signals = [ForeshadowSignal(
        arc_id="fs.core", status="overdue", importance=Importance.CORE, deadline_ch=5,
    )]
    assert decide_action(drift, signals) == "revise_l1"


def test_replanner_and_volume_review(tmp_path):
    ctx = NodeContext(llm=LLMClient(ScriptedProvider()))
    stores = {
        "mem": JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id"),
        "arc": JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id"),
        "summary": JsonStore(SummaryEntry, tmp_path / "s.jsonl", key_field="key"),
    }
    l0 = L0(logline="x", core_dramatic_question="q", ending_intent="e")
    l1 = L1(
        threads=[Thread(thread_id="th.main_road", tier="main", desc="成仙路")],
        foreshadow_map=[Foreshadow(fs_id="fs.origin", desc="身世")],
    )
    l2 = L2(
        vol_id="v1",
        chapter_beats=[
            ChapterBeat(planned_seq=1, event="入门"),
            ChapterBeat(planned_seq=4, event="收束"),
        ],
    )
    stores["arc"].append(ArcRecord(
        id="th.main_road", kind="thread", desc="成仙路", thread_state="OPEN",
    ))
    out = run_volume_review(
        ctx, chapter=4, vol_id="v1", l0=l0, l1=l1, l2=l2, stores=stores,
        chapters_in_volume=4,
    )
    assert out.volume_summary is not None
    assert stores["summary"].get("volume:v1") is not None
    assert out.action in ("hold", "patch_l2", "revise_l1")


def test_compute_drift_overdue_rate(tmp_path):
    arc = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    arc.append(ArcRecord(
        id="fs.a", kind="foreshadow", desc="a", state="PLANTED",
        importance=Importance.MINOR,
        payoff_deadline=PayoffDeadline(granularity="chapter", ref="c2"),
    ))
    arc.append(ArcRecord(
        id="fs.b", kind="foreshadow", desc="b", state="PLANTED",
        importance=Importance.MINOR,
        payoff_deadline=PayoffDeadline(granularity="chapter", ref="c20"),
    ))
    l1 = L1(threads=[Thread(thread_id="th.main", tier="main", desc="m")])
    drift = compute_drift(l1=l1, l2=None, arc_store=arc, chapter=5)
    assert drift.foreshadow_overdue_rate == 0.5
