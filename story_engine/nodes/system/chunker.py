"""Chunker（确定性分块）—— 对应 docs/nodes/system/chunker.md。

把 ChapterScript 切成 scene 对齐的可检索/可嵌入单元 + 稳定 chunk id + token 计数。
M1 只做确定性边界（为 M4 Embedder 铺路）；不做语义/滑窗切分。
chunk_id = scene_id，保证同一输入永远同一分块（可回归）。
"""

from __future__ import annotations

from dataclasses import dataclass

from story_engine.schemas.stores.script import ChapterScript
from story_engine.util.tokens import count_tokens


@dataclass
class Chunk:
    chunk_id: str        # = scene_id，稳定
    chapter: str
    text: str
    token_count: int
    beat_ids: list[str]


def chunk_chapter(script: ChapterScript) -> list[Chunk]:
    chunks: list[Chunk] = []
    for scene in script.scenes:
        text = "\n".join(b.content for b in scene.beats)
        chunks.append(
            Chunk(
                chunk_id=scene.scene_id,
                chapter=script.chapter,
                text=text,
                token_count=count_tokens(text),
                beat_ids=[b.beat_id for b in scene.beats],
            )
        )
    return chunks
