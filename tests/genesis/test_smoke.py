"""创世 smoke：seed → run_genesis → S₀ 就绪。验证控制流/数据流管道通。"""

from story_engine.orchestrator.genesis import run_genesis
from story_engine.schemas.artifacts.genesis_gap import GenesisVerdict
from story_engine.schemas.artifacts.seed import Seed


def _seed() -> Seed:
    return Seed(
        logline="荒古后裔叶凡踏上成仙路",
        genre=["东方玄幻"],
        tone=["悲壮"],
        ending_intent="揭穿成仙真相",
        protagonist_intent=["变强", "护同伴", "探真相"],
    )


def test_genesis_reaches_s0():
    result = run_genesis(_seed(), max_iter=3)
    assert result.ready
    assert result.gap.verdict == GenesisVerdict.PASS
    # S₀ 产物齐备
    assert result.l0.ending_intent == "揭穿成仙真相"
    assert result.l1.threads and result.l1.threads[0].tier == "main"
    assert result.world and all(w.definition for w in result.world)
    assert result.arcs  # ArcStore 台账已建
    # 台账含 thread(thread_state=OPEN) + foreshadow(state=PLANNED)
    by_kind = {a.kind: a for a in result.arcs}
    assert by_kind["thread"].thread_state == "OPEN"
    assert by_kind["foreshadow"].state == "PLANNED"
    # G4/G5：首卷大纲 + seed 画像（S₀ 产物清单齐备）
    assert result.l2 is not None and result.l2.vol_id == "v1"
    assert result.l2.chapter_beats
    assert result.profiles and all(p.t_valid == 0 for p in result.profiles)


def test_genesis_trace_has_stages():
    result = run_genesis(_seed())
    joined = " ".join(result.trace)
    for stage in ("G0", "G1", "G2", "G3", "G4", "G5"):
        assert stage in joined, f"缺阶段 {stage}"
