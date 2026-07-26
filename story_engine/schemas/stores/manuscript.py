"""ManuscriptStore：成品散文 —— 对应 ARCHITECTURE §1（成品层）。

冻结文档只给了「Writer 写 / 可重渲染覆盖 / 章节号为键」，未出精确字段表；
此处为 M2 最小落地（待评审）。成品层可重跑：同一 Script 换文风可重渲染覆盖。
"""

from __future__ import annotations

from story_engine.schemas.base import SchemaModel


class Manuscript(SchemaModel):
    chapter: str                        # c{n}，与 ChapterScript 同键
    text: str                           # 散文正文
    title: str | None = None
    style: str | None = None            # 本次渲染用的文风标签
    rendered_from: str | None = None    # 源 ChapterScript（= chapter，留作显式追溯）
    version: int = 1                    # 重渲染递增
