"""Temporal mixin UT：visible_as_of 语义。"""

from story_engine.schemas.base import Temporal
from story_engine.schemas.stores.memory import MemoryEntry


def test_memory_is_temporal():
    m = MemoryEntry(mem_id="m.x", scope="char:x", type="fact", text="t", t_valid=5)
    assert isinstance(m, Temporal)


def test_visible_as_of():
    m = MemoryEntry(mem_id="m.x", scope="char:x", type="fact", text="t", t_valid=5, t_invalid=10)
    assert not m.visible_as_of(4)    # 未生效
    assert m.visible_as_of(5)        # 生效当章
    assert m.visible_as_of(9)        # 有效
    assert not m.visible_as_of(10)   # 失效当章起不可见
    assert not m.visible_as_of(20)


def test_no_invalid_means_always_valid_after_tvalid():
    m = MemoryEntry(mem_id="m.y", scope="world", type="fact", text="t", t_valid=1)
    assert m.visible_as_of(1)
    assert m.visible_as_of(9999)
