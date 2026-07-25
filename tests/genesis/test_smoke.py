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
    # 台账含 thread(OPEN) + foreshadow(PLANNED)
    kinds = {a.kind: a.status for a in result.arcs}
    assert kinds.get("thread") == "OPEN"
    assert kinds.get("foreshadow") == "PLANNED"


def test_genesis_trace_has_stages():
    result = run_genesis(_seed())
    joined = " ".join(result.trace)
    assert "G0" in joined and "G1" in joined and "G2" in joined and "G5" in joined
