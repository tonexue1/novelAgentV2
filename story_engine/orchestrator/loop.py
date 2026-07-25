"""单章递推循环骨架 —— 对应受控递推 xᵢ=f(R(Sᵢ₋₁)); Sᵢ=U(Sᵢ₋₁,xᵢ)。

M0：只搭阶段管道（Plan → Direct → Character → Script → Gate → Record → Apply），
每阶段为 stub。真实节点逻辑留 M2/M3。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.nodes.base import NodeContext
from story_engine.primitives.ids import mint_chapter


@dataclass
class ChapterResult:
    chapter: str
    trace: list[str] = field(default_factory=list)


# 单章阶段顺序（M0 stub 管道）
_STAGES = ["plan", "direct", "character", "script", "gate", "record", "apply"]


def run_chapter(ctx: NodeContext, n: int) -> ChapterResult:
    chapter = mint_chapter(n)
    trace: list[str] = []
    for stage in _STAGES:
        # M0：仅记录阶段被触达；真实节点 M2/M3 接入。
        trace.append(f"{chapter}:{stage}")
    return ChapterResult(chapter=chapter, trace=trace)
