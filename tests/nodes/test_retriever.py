"""检索质量 UT —— 落实 EVALUATION §2.3 检索 fixture。

一条同时守：D3 召回 + C3 as-of 不泄漏 + A2 认知边界 + E 预算。
"""

from story_engine.nodes.system.retriever import Query, retrieve
from story_engine.schemas.stores.arc import ArcRecord, Knowledge
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.stores.json_backend import JsonStore


def _mem(mem_id, scope, type_, text, chapter, salience=0.7, tier=1):
    return MemoryEntry(
        id=mem_id, scope=scope, type=type_, text=text,
        t_valid=chapter, salience=salience, tier=tier,
    )


def _stores(tmp_path):
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "mem.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "arc.jsonl", key_field="id")
    return mem, arc


def test_recall_asof_boundary_budget(tmp_path):
    mem, arc = _stores(tmp_path)
    mem.append(_mem("m1", "char.ye_fan", "fact", "叶凡拜入青云门", 3))
    mem.append(_mem("m2", "char.ye_fan", "goal", "为父报仇", 1, salience=0.8))
    mem.append(_mem("m3", "char.ye_fan", "fact", "叶凡突破金丹", 50))   # 未来
    arc.append(ArcRecord(id="sec.blood", kind="secret", state="PLANTED",
                         desc="叶凡是魔族血脉",
                         knowledge=[Knowledge(char="char.pang_bo", since_ch=1)]))

    q = Query(as_of_chapter=20, char="char.ye_fan", focus="青云门 内斗", budget_tokens=4000)
    res = retrieve(q, mem, arc)
    ids = set(res.item_ids)

    assert "m1" in ids and "m2" in ids       # 召回：该记得的
    assert "m3" not in ids                    # as-of：未来泄漏被挡
    assert "sec.blood" not in ids             # 认知边界：不知的 secret 被挡


def test_budget_enforced(tmp_path):
    mem, arc = _stores(tmp_path)
    for i in range(3):
        mem.append(_mem(f"m{i}", "char.x", "fact", "长" * 200, 1, salience=0.5 + i * 0.1))
    q = Query(as_of_chapter=5, char="char.x", budget_tokens=250)
    res = retrieve(q, mem, arc)
    assert len(res.items) < 3
    assert len(res.dropped) >= 1
    assert "m2" in res.item_ids


def test_goal_ranks_high(tmp_path):
    mem, arc = _stores(tmp_path)
    mem.append(_mem("m_fact", "char.x", "fact", "路过集市", 1, salience=0.5))
    mem.append(_mem("m_goal", "char.x", "goal", "变强", 1, salience=0.5))
    q = Query(as_of_chapter=5, char="char.x", budget_tokens=4000)
    res = retrieve(q, mem, arc)
    assert res.item_ids[0] == "m_goal"


def test_deterministic_order(tmp_path):
    mem, arc = _stores(tmp_path)
    for i in range(5):
        mem.append(_mem(f"m{i}", "char.x", "fact", f"事件{i}", 1, salience=0.5))
    q = Query(as_of_chapter=5, char="char.x", budget_tokens=4000)
    r1 = retrieve(q, mem, arc)
    r2 = retrieve(q, mem, arc)
    assert r1.item_ids == r2.item_ids


def test_must_always_included_even_over_bucket(tmp_path):
    mem, arc = _stores(tmp_path)
    mem.append(_mem("m_goal", "char.x", "goal", "长" * 300, 1, salience=0.9))
    mem.append(_mem("m_fact", "char.x", "fact", "小事", 1, salience=0.5))
    q = Query(as_of_chapter=5, char="char.x", budget_tokens=50)
    res = retrieve(q, mem, arc)
    assert "m_goal" in res.item_ids
    assert res.over_budget is True
    assert res.priorities["m_goal"] == "MUST"


def test_bucket_subbudget_fair_share(tmp_path):
    mem, arc = _stores(tmp_path)
    mem.append(_mem("s1", "char.x", "fact", "长" * 40, 5, salience=0.6))
    mem.append(_mem("s2", "char.x", "fact", "长" * 40, 5, salience=0.55))
    mem.append(_mem("c1", "char.x", "trait", "长" * 40, 1, salience=0.6))
    q = Query(as_of_chapter=5, char="char.x", budget_tokens=400,
              bucket_weights={"streaming": 0.05, "character": 0.4, "trajectory": 0.4})
    res = retrieve(q, mem, arc)
    assert "c1" in res.item_ids
    assert res.priorities["s1"] == "SHOULD"
