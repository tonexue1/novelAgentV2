"""Applier（确定性落库）—— M0 stub。

真实职责：把上游产物确定性写入各 store（建 ArcStore 台账、定 beat 序、写 memory）。
见 docs/nodes/system/applier.md。
M0 stub：据 L1 建初始 ArcStore 台账（thread→OPEN、foreshadow→PLANNED）。
"""

from __future__ import annotations

from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.plan import L1


class ApplierStub:
    name = "applier"

    def init_arcs(self, l1: L1) -> list[ArcRecord]:
        arcs: list[ArcRecord] = []
        for t in l1.threads:
            arcs.append(
                ArcRecord(arc_id=t.thread_id, kind="thread", status="OPEN", desc=t.desc)
            )
        for fs in l1.foreshadow_map:
            arcs.append(
                ArcRecord(arc_id=fs.fs_id, kind="foreshadow", status="PLANNED", desc=fs.desc)
            )
        return arcs
