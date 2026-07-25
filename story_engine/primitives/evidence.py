"""EvidenceSpan / StoryTime —— 对应 docs/schema/primitives/common.md。

EvidenceSpan 是守 U 的寻址基元：一切派生条目须回指已提交的 ScriptStore 位置。
简写串： c12 / c12.s3 / c12.s3.b5 / c12.s3.b5-8
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field, model_validator

_SPAN_RE = re.compile(r"^c(\d+)(?:\.s(\d+)(?:\.b(\d+)(?:-(\d+))?)?)?$")


class EvidenceSpan(BaseModel):
    """回指 ScriptStore 位置。chapter 必填；scene 省略=整章；beats 省略=整场。"""

    chapter: int = Field(..., ge=0)
    scene: int | None = Field(default=None, ge=1)  # 场号 1-indexed
    beats: tuple[int, int] | None = None  # [from, to]，闭区间，1-indexed

    @model_validator(mode="after")
    def _check(self) -> "EvidenceSpan":
        if self.beats is not None:
            if self.scene is None:
                raise ValueError("beats 存在时 scene 必填")
            lo, hi = self.beats
            if lo < 1:
                raise ValueError(f"beat 序号 1-indexed，lo 须 ≥1: {self.beats}")
            if lo > hi:
                raise ValueError(f"beats 区间非法: {self.beats}")
        return self

    @classmethod
    def parse(cls, s: str) -> "EvidenceSpan":
        """从简写串解析，如 'c12.s3.b5-8'。"""
        m = _SPAN_RE.match(s.strip())
        if not m:
            raise ValueError(f"非法 evidence 串: {s!r}")
        ch, sc, b_from, b_to = m.groups()
        beats = None
        if b_from is not None:
            lo = int(b_from)
            hi = int(b_to) if b_to is not None else lo
            beats = (lo, hi)
        return cls(
            chapter=int(ch),
            scene=int(sc) if sc is not None else None,
            beats=beats,
        )

    def to_str(self) -> str:
        s = f"c{self.chapter}"
        if self.scene is not None:
            s += f".s{self.scene}"
            if self.beats is not None:
                lo, hi = self.beats
                s += f".b{lo}" if lo == hi else f".b{lo}-{hi}"
        return s

    def __str__(self) -> str:  # pragma: no cover - 便捷
        return self.to_str()


class StoryTime(BaseModel):
    """叙事内时间，供时间线硬检。全部可选。"""

    day: int | None = None
    clock: str | None = None  # "黄昏" / "三更" / "10:30"
    relative: str | None = None  # "三日后" / "同一时刻"
