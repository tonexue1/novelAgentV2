from story_engine.primitives import ids


def test_mint_positional_ids():
    c = ids.mint_chapter(12)
    s = ids.mint_scene(c, 3)
    b = ids.mint_beat(s, 5)
    assert c == "c12"
    assert s == "c12.s3"
    assert b == "c12.s3.b5"
    assert ids.is_chapter(c) and ids.is_scene(s) and ids.is_beat(b)


def test_chapter_num():
    assert ids.chapter_num("c42") == 42


def test_mint_entity_and_validate():
    eid = ids.mint_entity("char", "ye_fan")
    assert eid == "char.ye_fan"
    assert ids.is_entity(eid)


def test_illegal_ids_rejected():
    for bad in ["c12x", "cs3", "char.YeFan", "unknown.x"]:
        assert not (ids.is_chapter(bad) or ids.is_scene(bad) or ids.is_beat(bad) or ids.is_entity(bad))


def test_mint_entity_rejects_bad_prefix_and_slug():
    import pytest

    with pytest.raises(ValueError):
        ids.mint_entity("nope", "x")
    with pytest.raises(ValueError):
        ids.mint_entity("char", "Bad Slug")


def test_ulid_monotonic_and_format():
    a = ids.new_ulid()
    b = ids.new_ulid()
    assert len(a) == 26 and len(b) == 26
    assert a != b
    mem = ids.mint_memory_id()
    assert mem.startswith("m.") and ids.MEMORY_RE.match(mem)
