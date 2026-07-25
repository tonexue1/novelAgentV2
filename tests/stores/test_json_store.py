from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.stores.json_backend import JsonStore


def _mem(mem_id: str, t_valid: int, t_invalid=None) -> MemoryEntry:
    return MemoryEntry(
        mem_id=mem_id,
        scope="char:ye_fan",
        type="fact",
        text=f"fact {mem_id}",
        t_valid=t_valid,
        t_invalid=t_invalid,
    )


def test_append_get_persist(tmp_path):
    path = tmp_path / "mem.jsonl"
    store: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, path, key_field="mem_id")
    store.append(_mem("m.A", 1))
    store.append(_mem("m.B", 5))
    assert len(store) == 2
    assert store.get("m.A").text == "fact m.A"

    # 重新加载后仍在（持久化）
    store2: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, path, key_field="mem_id")
    assert len(store2) == 2
    assert store2.get("m.B").t_valid == 5


def test_as_of_no_future_leakage(tmp_path):
    store: JsonStore[MemoryEntry] = JsonStore(
        MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id"
    )
    store.append(_mem("m.past", 3))
    store.append(_mem("m.future", 50))       # 未来事实
    store.append(_mem("m.invalidated", 2, t_invalid=10))  # 第10章已软失效

    at20 = {m.mem_id for m in store.as_of(20)}
    assert "m.past" in at20            # 已生效
    assert "m.future" not in at20      # 未来泄漏被挡
    assert "m.invalidated" not in at20  # 已软失效被挡


def test_query_filter(tmp_path):
    store: JsonStore[MemoryEntry] = JsonStore(
        MemoryEntry, tmp_path / "m.jsonl", key_field="mem_id"
    )
    store.append(_mem("m.A", 1))
    got = store.query(scope="char:ye_fan")
    assert len(got) == 1
