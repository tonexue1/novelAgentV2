"""Chunker 确定性 UT：scene 对齐、稳定 id、token 计数。"""

from story_engine.nodes.system.chunker import chunk_chapter
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene


def _script():
    return ChapterScript(
        chapter="c1",
        scenes=[
            Scene(scene_id="c1.s1", beats=[
                Beat(beat_id="c1.s1.b1", content="叶凡走进青云门"),
                Beat(beat_id="c1.s1.b2", content="他看见了庞博"),
            ]),
            Scene(scene_id="c1.s2", beats=[Beat(beat_id="c1.s2.b1", content="夜幕降临")]),
        ],
    )


def test_scene_aligned_chunks():
    chunks = chunk_chapter(_script())
    assert [c.chunk_id for c in chunks] == ["c1.s1", "c1.s2"]
    assert chunks[0].beat_ids == ["c1.s1.b1", "c1.s1.b2"]
    assert all(c.chapter == "c1" for c in chunks)


def test_deterministic_and_token_count():
    c1 = chunk_chapter(_script())
    c2 = chunk_chapter(_script())
    assert [c.chunk_id for c in c1] == [c.chunk_id for c in c2]
    assert all(c.token_count > 0 for c in c1)
