"""伏笔临期/逾期 surfacing —— 对应 docs/schema/stores/arc-store.md 收束保证。

确定性计算 due/overdue；core 逾期单独标出供 Gate / Replanner BLOCK。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from story_engine.primitives.enums import Importance

ForeshadowStatus = Literal["due", "overdue"]


@dataclass
class ForeshadowSignal:
    arc_id: str
    status: ForeshadowStatus
    importance: Importance
    deadline_ch: int
    desc: str = ""

    @property
    def is_core_overdue(self) -> bool:
        return self.status == "overdue" and self.importance == Importance.CORE


def resolve_deadline_chapter(
    deadline,
    *,
    l2=None,
    volume_end_ch: int | None = None,
    saga_end_ch: int | None = None,
) -> int | None:
    """把 payoff_deadline 解析为到期章号下界。无法解析则 None。"""
    if deadline is None:
        return None
    gran = deadline.granularity
    ref = str(deadline.ref)
    if gran == "chapter":
        try:
            return int(ref.lstrip("c"))
        except ValueError:
            return None
    if gran == "volume":
        if volume_end_ch is not None:
            return volume_end_ch
        if l2 is not None and l2.chapter_beats:
            return max(b.planned_seq for b in l2.chapter_beats)
        # ref 形如 v1 —— 无更多信息时无法解析
        return None
    if gran == "saga":
        return saga_end_ch
    return None


def surface_foreshadows(
    arc_store,
    chapter: int,
    *,
    l2=None,
    volume_end_ch: int | None = None,
    saga_end_ch: int | None = None,
    chapter_window: int = 2,
    volume_window: int = 3,
) -> list[ForeshadowSignal]:
    """返回临期 + 逾期伏笔清单（未终态）。"""
    out: list[ForeshadowSignal] = []
    for rec in arc_store.all():
        if rec.kind != "foreshadow" or rec.state in {"FULFILLED", "ABANDONED"}:
            continue
        deadline_ch = resolve_deadline_chapter(
            rec.payoff_deadline,
            l2=l2,
            volume_end_ch=volume_end_ch,
            saga_end_ch=saga_end_ch,
        )
        if deadline_ch is None:
            continue
        gran = rec.payoff_deadline.granularity if rec.payoff_deadline else "chapter"
        window = volume_window if gran in ("volume", "saga") else chapter_window
        imp = rec.importance or Importance.MINOR
        if chapter >= deadline_ch:
            out.append(ForeshadowSignal(
                arc_id=rec.id, status="overdue", importance=imp,
                deadline_ch=deadline_ch, desc=rec.desc,
            ))
        elif chapter >= deadline_ch - window:
            out.append(ForeshadowSignal(
                arc_id=rec.id, status="due", importance=imp,
                deadline_ch=deadline_ch, desc=rec.desc,
            ))
    return out


def core_overdue(signals: list[ForeshadowSignal]) -> list[ForeshadowSignal]:
    return [s for s in signals if s.is_core_overdue]
