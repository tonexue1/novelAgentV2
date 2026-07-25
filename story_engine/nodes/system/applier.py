"""Applier（确定性落库）—— 对应 docs/nodes/system/applier.md + arc-store 状态机。

U（固化）的确定性半边：抽取是 LLM（Extractor, M2），应用是确定性（本节点, M1）。
职责：
  - beat 定序：ChapterScript 提交时铸永久 beat id。
  - 应用 RecorderOutput：MemOp → MemoryStore（ADD/REINFORCE/SOFT-INVALIDATE/NOOP）、
    ArcOp → ArcStore 状态机转移（含守卫、history 回溯、secret REVEAL）。
  - 据 L1 建初始 ArcStore 台账（创世用）。
状态机守卫：非法转移（如 FULFILL 未 PLANT、改动终态）直接 raise，fail-fast。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.primitives.ids import mint_beat, mint_memory_id
from story_engine.schemas.artifacts.recorder_output import ArcOp, MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord, ArcTransition, Knowledge, ThreadAdvance
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L1
from story_engine.schemas.stores.script import ChapterScript

# fs/秘密状态机：op → (合法前态集, 新态)
_FS_TRANS = {
    "PLANT": ({"PLANNED"}, "PLANTED"),
    "REINFORCE": ({"PLANTED", "REINFORCED"}, "REINFORCED"),
    "FULFILL": ({"PLANTED", "REINFORCED"}, "FULFILLED"),
}
_FS_TERMINAL = {"FULFILLED", "ABANDONED"}
# thread 状态机
_THREAD_TRANS = {
    "ADVANCE": ({"OPEN", "ADVANCING"}, "ADVANCING"),
    "CLIMAX": ({"ADVANCING"}, "CLIMAX"),
    "RESOLVE": ({"CLIMAX"}, "RESOLVED"),
}
_THREAD_TERMINAL = {"RESOLVED", "DROPPED"}


@dataclass
class ApplyResult:
    added_mem: list[str] = field(default_factory=list)
    reinforced_mem: list[str] = field(default_factory=list)
    invalidated_mem: list[str] = field(default_factory=list)
    arc_transitions: list[tuple[str, str]] = field(default_factory=list)  # (id, new_state)
    noops: list[str] = field(default_factory=list)                        # 留档供审计


class Applier:
    name = "applier"

    # ── 创世：据 L1 建初始台账 ──────────────────────────────
    def init_arcs(self, l1: L1) -> list[ArcRecord]:
        arcs: list[ArcRecord] = []
        for t in l1.threads:
            arcs.append(
                ArcRecord(
                    id=t.thread_id, kind="thread", desc=t.desc,
                    origin="planned", thread_state="OPEN", tier=t.tier,
                )
            )
        for fs in l1.foreshadow_map:
            arcs.append(
                ArcRecord(
                    id=fs.fs_id, kind="foreshadow", desc=fs.desc,
                    origin="planned", state="PLANNED", importance=fs.importance,
                    payoff_deadline=fs.payoff_deadline,
                )
            )
        return arcs

    # ── beat 定序 ──────────────────────────────────────────
    def assign_beat_ids(self, script: ChapterScript) -> ChapterScript:
        for scene in script.scenes:
            for k, beat in enumerate(scene.beats, start=1):
                beat.beat_id = mint_beat(scene.scene_id, k)
        return script

    # ── 应用抽取增量 ────────────────────────────────────────
    def apply_recorder_output(self, ro: RecorderOutput, mem_store, arc_store) -> ApplyResult:
        result = ApplyResult()
        for op in ro.mem_ops:
            self._apply_mem_op(op, ro.chapter, mem_store, result)
        for op in ro.arc_ops:
            self._apply_arc_op(op, ro.chapter, arc_store, result)
        return result

    # ── MemOp ───────────────────────────────────────────────
    def _apply_mem_op(self, op: MemOp, chapter: int, mem_store, result: ApplyResult) -> None:
        if op.action == "NOOP":
            result.noops.append(op.target_id or "mem")
            return
        if op.action == "ADD":
            entry = MemoryEntry(
                id=mint_memory_id(),
                type=op.type or "fact",
                scope=op.scope or "global",
                text=op.text or "",
                t_valid=chapter,
                strength=op.strength,
                evidence=list(op.evidence),
                involves=list(op.involves),
                salience=op.salience,
                goal_kind=op.goal_kind,
                parent=op.parent,
                example=op.example,
            )
            mem_store.append(entry)
            result.added_mem.append(entry.id)
        elif op.action == "REINFORCE":
            target = mem_store.get(op.target_id) if op.target_id else None
            if target is None:
                raise ValueError(f"REINFORCE 目标不存在: {op.target_id}")
            changes: dict = {"evidence": target.evidence + list(op.evidence)}
            if op.strength is not None:
                changes["strength"] = op.strength
            mem_store.update(op.target_id, **changes)
            result.reinforced_mem.append(op.target_id)
        elif op.action == "SOFT-INVALIDATE":
            if op.target_id and mem_store.get(op.target_id) is not None:
                mem_store.update(op.target_id, t_invalid=chapter, resolution=op.resolution)
                result.invalidated_mem.append(op.target_id)

    # ── ArcOp（状态机守卫）──────────────────────────────────
    def _apply_arc_op(self, op: ArcOp, chapter: int, arc_store, result: ApplyResult) -> None:
        if op.op == "NOOP":
            result.noops.append(op.target_id)
            return

        rec = arc_store.get(op.target_id)
        if rec is None:
            if op.is_new:
                rec = self._create_from_draft(op, chapter)
                arc_store.append(rec)
            else:
                raise ValueError(f"arc {op.target_id} 不存在且非 is_new，禁止凭空转移")

        if op.op == "REVEAL":
            self._apply_reveal(op, chapter, rec, arc_store, result)
            return

        if rec.kind == "thread":
            self._transition_thread(op, chapter, rec, arc_store, result)
        else:
            self._transition_fs(op, chapter, rec, arc_store, result)

    def _create_from_draft(self, op: ArcOp, chapter: int) -> ArcRecord:
        draft = op.draft or {}
        if op.kind == "thread":
            return ArcRecord(
                id=op.target_id, kind="thread", desc=draft.get("desc", ""),
                origin="emergent", established_ch=chapter,
                thread_state="OPEN", tier=draft.get("tier"),
            )
        return ArcRecord(
            id=op.target_id, kind=op.kind, desc=draft.get("desc", ""),
            origin="emergent", established_ch=chapter,
            state="PLANNED", importance=draft.get("importance"),
        )

    def _apply_reveal(self, op, chapter, rec, arc_store, result) -> None:
        knowledge = list(rec.knowledge) + [
            Knowledge(char=c, since_ch=chapter, evidence=list(op.evidence)) for c in op.reveal_to
        ]
        history = rec.history + [ArcTransition(ch=chapter, transition="REVEAL", evidence=list(op.evidence))]
        arc_store.update(op.target_id, knowledge=knowledge, history=history)
        result.arc_transitions.append((op.target_id, "REVEAL"))

    def _transition_fs(self, op, chapter, rec, arc_store, result) -> None:
        if op.op == "ABANDON":
            if rec.state in _FS_TERMINAL:
                raise ValueError(f"{op.target_id} 已终态 {rec.state}，不可 ABANDON")
            if not op.abandon_reason:
                raise ValueError("ABANDON 必带 abandon_reason（绝不静默悬空）")
            changes = {"state": "ABANDONED", "abandon_reason": op.abandon_reason}
            new_state = "ABANDONED"
        elif op.op in _FS_TRANS:
            allowed, new_state = _FS_TRANS[op.op]
            if rec.state not in allowed:
                raise ValueError(f"{op.target_id} 状态 {rec.state} 不允许 {op.op}（需前态 {allowed}）")
            changes = {"state": new_state}
            if op.op == "PLANT":
                changes["plant_evidence"] = rec.plant_evidence + list(op.evidence)
            elif op.op == "FULFILL":
                changes["fulfill_evidence"] = rec.fulfill_evidence + list(op.evidence)
        else:
            raise ValueError(f"op {op.op} 不适用于 {rec.kind}")
        changes["history"] = rec.history + [
            ArcTransition(ch=chapter, transition=op.op, evidence=list(op.evidence))
        ]
        arc_store.update(op.target_id, **changes)
        result.arc_transitions.append((op.target_id, new_state))

    def _transition_thread(self, op, chapter, rec, arc_store, result) -> None:
        if op.op == "DROP":
            if rec.thread_state in _THREAD_TERMINAL:
                raise ValueError(f"{op.target_id} 已终态 {rec.thread_state}，不可 DROP")
            if not op.abandon_reason:
                raise ValueError("DROP 必带 abandon_reason")
            changes = {"thread_state": "DROPPED", "abandon_reason": op.abandon_reason}
            new_state = "DROPPED"
        elif op.op in _THREAD_TRANS:
            allowed, new_state = _THREAD_TRANS[op.op]
            if rec.thread_state not in allowed:
                raise ValueError(
                    f"{op.target_id} 状态 {rec.thread_state} 不允许 {op.op}（需前态 {allowed}）"
                )
            changes = {"thread_state": new_state}
            if op.op == "ADVANCE":
                changes["advances"] = rec.advances + [
                    ThreadAdvance(ch=chapter, milestone=op.milestone or "", evidence=list(op.evidence))
                ]
        else:
            raise ValueError(f"op {op.op} 不适用于 thread")
        changes["history"] = rec.history + [
            ArcTransition(ch=chapter, transition=op.op, evidence=list(op.evidence))
        ]
        arc_store.update(op.target_id, **changes)
        result.arc_transitions.append((op.target_id, new_state))


# 兼容旧引用
ApplierStub = Applier
