"""M2 垂直切片：seed → 创世 → 连跑第 1、2 章 → 散文 + 记忆入库。

全程走假 LLM（无网络、零成本）。验的是**接线与契约**，不是文笔。
第 2 章是 Reconciler 的实测点：第 1 章几乎没有旧档案可对账。
"""

from story_engine.llm.base import LLMClient
from story_engine.nodes.base import NodeContext
from story_engine.orchestrator.genesis import run_genesis
from story_engine.orchestrator.loop import run_chapter
from story_engine.schemas.artifacts.seed import Seed
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.manuscript import Manuscript
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.script import ChapterScript
from story_engine.stores.json_backend import JsonStore
from story_engine.telemetry.runrecord import Telemetry
from tests.fake_llm import ScriptedProvider


def _seed() -> Seed:
    return Seed(
        logline="荒古后裔叶凡踏上成仙路",
        genre=["东方玄幻"],
        tone=["悲壮"],
        ending_intent="揭穿成仙真相",
        protagonist_intent=["变强", "护同伴"],
    )


def _setup(tmp_path):
    tel = Telemetry()
    ctx = NodeContext(llm=LLMClient(ScriptedProvider(), telemetry=tel), telemetry=tel)
    stores = {
        "script": JsonStore(ChapterScript, tmp_path / "script.jsonl", key_field="chapter"),
        "mem": JsonStore(MemoryEntry, tmp_path / "mem.jsonl", key_field="id"),
        "arc": JsonStore(ArcRecord, tmp_path / "arc.jsonl", key_field="id"),
        "manuscript": JsonStore(Manuscript, tmp_path / "ms.jsonl", key_field="chapter"),
    }
    return ctx, stores, tel


def _genesis(ctx, stores):
    result = run_genesis(_seed(), ctx=ctx)
    for arc in result.arcs:
        stores["arc"].append(arc)
    for profile in result.profiles:
        stores["mem"].append(profile)
    return result


def test_genesis_with_llm_reaches_s0(tmp_path):
    ctx, stores, _ = _setup(tmp_path)
    result = _genesis(ctx, stores)
    assert result.ready
    # id 前缀由系统规整：LLM 报的是裸 slug
    assert result.l1.threads[0].thread_id == "th.main_road"
    assert result.l1.foreshadow_map[0].fs_id == "fs.origin"
    assert {w.entity_id for w in result.world} == set(result.l1.world_refs)

    # G4：L2[卷1] —— 卷号系统覆盖、幽灵 thread 被滤掉、planned_seq 重排连号
    assert result.l2 is not None and result.l2.vol_id == "v1"
    assert [t.thread_id for t in result.l2.thread_targets] == ["th.main_road"]
    assert result.l2.volume_spine is not None
    assert [cb.planned_seq for cb in result.l2.chapter_beats] == [1, 2, 3, 4]
    assert {cb.touches_spine for cb in result.l2.chapter_beats} >= {
        "inciting", "midpoint", "climax",
    }

    # G5：seed 画像 —— 只种 character_arcs 收录的角色，evidence 指 c0（创世）
    assert result.profiles
    assert {p.scope for p in result.profiles} == {"char.ye_fan"}
    assert all(p.tier == 0 and p.t_valid == 0 for p in result.profiles)
    assert all(e.chapter == 0 for p in result.profiles for e in p.evidence)


def test_chapter_one_end_to_end(tmp_path):
    ctx, stores, tel = _setup(tmp_path)
    g = _genesis(ctx, stores)

    res = run_chapter(ctx, 1, l0=g.l0, l1=g.l1, l2=g.l2, world=g.world, stores=stores)

    # 主真相落库，位置 id 严格连号
    script = stores["script"].get("c1")
    assert script is not None and script.scenes
    scene = script.scenes[0]
    assert scene.scene_id == "c1.s1"
    assert [b.beat_id for b in scene.beats] == ["c1.s1.b1", "c1.s1.b2"]
    assert all(b.dramatic_goal for b in scene.beats)      # 派工段持久化作证据链
    assert scene.contract_ref == scene.scene_id

    # 承重拍 id 被系统重铸成场景内定位，Beat.hits 回指得上
    obligations = {o.obligation_id for o in res.scene_script.scenes[0].obligations}
    assert obligations == {"c1.s1.o1", "c1.s1.o2"}
    assert {b.hits for b in scene.beats} <= obligations

    # 一致性闸未接（M3）→ 本章并未过闸，不许标 clean
    assert script.consistency_status == "flagged"

    # 消费层出散文
    assert stores["manuscript"].get("c1").text

    # 忠实性校验拦掉了指向不存在拍的候选：新入库的只有 1 条（seed 画像之外）
    assert any(r["stage"] == "span" for r in res.rejected)
    assert len(stores["mem"].all()) == len(g.profiles) + 1

    assert tel.total_tokens() > 0


def test_skip_writer_still_records(tmp_path):
    ctx, stores, _ = _setup(tmp_path)
    g = _genesis(ctx, stores)
    res = run_chapter(
        ctx, 1, l0=g.l0, l1=g.l1, l2=g.l2, world=g.world, stores=stores,
        skip_writer=True,
    )
    assert res.manuscript is None
    assert stores["manuscript"].get("c1") is None
    assert stores["script"].get("c1") is not None
    assert "跳过 Writer" in res.trace[-3] or any("跳过 Writer" in t for t in res.trace)


def test_chapter_two_triggers_reconcile(tmp_path):
    """第 2 章重复抽到同一事实 → 对账判 REINFORCE，不产生第二条记录。"""
    ctx, stores, _ = _setup(tmp_path)
    g = _genesis(ctx, stores)
    baseline = len(g.profiles)

    run_chapter(ctx, 1, l0=g.l0, l1=g.l1, l2=g.l2, world=g.world, stores=stores)
    assert len(stores["mem"].all()) == baseline + 1

    run_chapter(ctx, 2, l0=g.l0, l1=g.l1, l2=g.l2, world=g.world, stores=stores)

    after = stores["mem"].all()
    assert len(after) == baseline + 1                       # 没被重复 ADD
    fact = next(m for m in after if m.text == "叶凡拜入青云门")
    assert len(fact.evidence) == 2                          # 第 2 章的出处被加强进去
    assert stores["script"].get("c2") is not None
    assert stores["manuscript"].get("c2") is not None
