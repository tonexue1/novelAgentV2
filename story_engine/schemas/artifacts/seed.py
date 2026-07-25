"""Seed：创世种子 —— 对应 docs/schema/artifacts/seed.md。

创世 flow（ARCHITECTURE §2.6）唯一人工输入契约。必填 5 项 + 可选 3 项。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.schemas.base import SchemaModel


class LengthTarget(SchemaModel):
    unit: Literal["chapter", "volume"]
    count: int


class Seed(SchemaModel):
    # ── 必填（创世最小锚集）──
    logline: str
    genre: list[str]
    tone: list[str]
    ending_intent: str
    protagonist_intent: list[str]

    # ── 可选（缺省系统补 / 跑时长）──
    hard_rules: list[str] = Field(default_factory=list)
    length_target: LengthTarget | None = None
    refs: list[str] = Field(default_factory=list)
