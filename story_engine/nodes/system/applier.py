"""Applier（确定性落库）—— 对应 docs/nodes/system/applier.md。

U（固化）的确定性半边：抽取是 LLM（Extractor, M2），应用是确定性（本节点, M1）。
职责：
  - beat 定序：ChapterScript 提交时铸永久 beat id。
  - 应用 RecorderOutput：MemOp → MemoryStore（含软失效）、ArcOp → ArcStore 状态机转移。
  - 据 L1 建初始 ArcStore 台账（创世用）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.primitives.ids import mint_beat, mint_memory_id
from story_engine.schemas.artifacts.recorder_output import ArcOp, MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L1
from story_engine.schemas.stores.script import ChapterScript

# ArcOp.op → ArcRecord.status
_ARC_STATUS = {
    "OPEN": "OPEN",
    "PLANT": "PLANTED",
    "REINFORCE": "REINFORCED",
    "FULFILL": "FULFILLED",
    "ABANDON": "ABANDONED",
}


@dataclass
class ApplyResult:
    added_mem: list[str] = field(default_factory=list)
    invalidated_mem: list[str] = field(default_factory=list)
    arc_transitions: list[tuple[str, str]] = field(default_factory=list)  # (arc_id, new_status)


class Applier:
    name = "applier"

    # ── 创世：据 L1 建初始台账 ──────────────────────────────
    def init_arcs(self, l1: L1) -> list[ArcRecord]:
        arcs: list[ArcRecord] = []
        for t in l1.threads:
            arcs.append(ArcRecord(arc_id=t.thread_id, kind="thread", status="OPEN", desc=t.desc))
        for fs in l1.foreshadow_map:
            arcs.append(
                ArcRecord(arc_id=fs.fs_id, kind="foreshadow", status="PLANNED", desc=fs.desc)
            )
        return arcs

    # ── beat 定序 ──────────────────────────────────────────
    def assign_beat_ids(self, script: ChapterScript) -> ChapterScript:
        """确定性铸 beat id：c{n}.s{m}.b{k}，场内从 1 递增。"""
        for scene in script.scenes:
            for k, beat in enumerate(scene.beats, start=1):
                beat.beat_id = mint_beat(scene.scene_id, k)
        return script

    # ── 应用抽取增量 ────────────────────────────────────────
    def apply_recorder_output(
        self,
        ro: RecorderOutput,
        mem_store,   # JsonStore[MemoryEntry]
        arc_store,   # JsonStore[ArcRecord]
    ) -> ApplyResult:
        result = ApplyResult()
        for op in ro.mem_ops:
            self._apply_mem_op(op, ro.chapter, mem_store, result)
        for op in ro.arc_ops:
            self._apply_arc_op(op, arc_store, result)
        return result

    def _apply_mem_op(self, op: MemOp, chapter: int, mem_store, result: ApplyResult) -> None:
        if op.op == "NOOP":
            return
        if op.op == "ADD":
            entry = MemoryEntry(
                mem_id=mint_memory_id(),
                scope=op.scope or "world",
                type=op.type or "fact",
                text=op.text or "",
                salience=op.salience,
                t_valid=chapter,
                evidence=list(op.evidence),
                parent=op.parent,
            )
            mem_store.append(entry)
            result.added_mem.append(entry.mem_id)
        elif op.op == "INVALIDATE":
            if op.target_mem_id and mem_store.get(op.target_mem_id) is not None:
                mem_store.update(op.target_mem_id, t_invalid=chapter)
                result.invalidated_mem.append(op.target_mem_id)

    def _apply_arc_op(self, op: ArcOp, arc_store, result: ApplyResult) -> None:
        if op.op == "NOOP":
            return
        new_status = _ARC_STATUS[op.op]
        existing = arc_store.get(op.arc_id)
        if existing is None:
            arc_store.append(
                ArcRecord(
                    arc_id=op.arc_id,
                    kind=op.kind,
                    status=new_status,
                    desc=op.desc or "",
                    known_by=list(op.known_by),
                    hidden_from=list(op.hidden_from),
                    evidence=list(op.evidence),
                )
            )
        else:
            arc_store.update(op.arc_id, status=new_status)
        result.arc_transitions.append((op.arc_id, new_status))


# 兼容旧引用（M0 genesis 用 ApplierStub）
ApplierStub = Applier
