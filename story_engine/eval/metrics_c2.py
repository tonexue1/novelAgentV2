"""C2 伏笔闭环 + script 闸门代理。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from story_engine.nodes.system.foreshadow import surface_foreshadows
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.script import ChapterScript


class _ArcList:
    """surface_foreshadows 只需 .all()。"""

    def __init__(self, items: list[ArcRecord]) -> None:
        self._items = items

    def all(self) -> list[ArcRecord]:
        return list(self._items)


class C2Metrics(BaseModel):
    available: bool = False
    as_of_chapter: int | None = None
    foreshadow_total: int = 0
    foreshadow_active: int = 0
    foreshadow_fulfilled: int = 0
    foreshadow_abandoned: int = 0
    closed_rate: float | None = None          # fulfilled / total
    settled_rate: float | None = None         # (fulfilled+abandoned) / total
    overdue_count: int = 0
    core_overdue_count: int = 0
    due_count: int = 0


class ScriptGateMetrics(BaseModel):
    available: bool = False
    chapters: int = 0
    clean: int = 0
    flagged: int = 0
    other: dict[str, int] = Field(default_factory=dict)


def compute_c2(
    arcs: list[ArcRecord] | None,
    *,
    available: bool,
    as_of: int | None,
) -> C2Metrics:
    if not available:
        return C2Metrics(available=False, as_of_chapter=as_of)
    arcs = arcs or []
    fs = [a for a in arcs if a.kind == "foreshadow"]
    total = len(fs)
    fulfilled = sum(1 for a in fs if a.state == "FULFILLED")
    abandoned = sum(1 for a in fs if a.state == "ABANDONED")
    active = sum(1 for a in fs if a.state not in {"FULFILLED", "ABANDONED"})
    closed = round(fulfilled / total, 4) if total else None
    settled = round((fulfilled + abandoned) / total, 4) if total else None

    overdue = due = core_od = 0
    if as_of is not None:
        signals = surface_foreshadows(_ArcList(arcs), as_of)
        due = sum(1 for s in signals if s.status == "due")
        overdue = sum(1 for s in signals if s.status == "overdue")
        core_od = sum(1 for s in signals if s.is_core_overdue)

    return C2Metrics(
        available=True,
        as_of_chapter=as_of,
        foreshadow_total=total,
        foreshadow_active=active,
        foreshadow_fulfilled=fulfilled,
        foreshadow_abandoned=abandoned,
        closed_rate=closed,
        settled_rate=settled,
        overdue_count=overdue,
        core_overdue_count=core_od,
        due_count=due,
    )


def compute_script_gate(scripts: list[ChapterScript] | None, *, available: bool) -> ScriptGateMetrics:
    if not available:
        return ScriptGateMetrics(available=False)
    scripts = scripts or []
    clean = flagged = 0
    other: dict[str, int] = {}
    for s in scripts:
        st = s.consistency_status
        if st == "clean":
            clean += 1
        elif st == "flagged":
            flagged += 1
        else:
            other[str(st)] = other.get(str(st), 0) + 1
    return ScriptGateMetrics(
        available=True,
        chapters=len(scripts),
        clean=clean,
        flagged=flagged,
        other=other,
    )
