"""Applier（确定性落库）—— 对应 docs/nodes/system/applier.md + arc/world/summary 状态机。

U（固化）的确定性半边：抽取是 LLM（Extractor, M2），应用是确定性（本节点）。
职责：
  - beat 定序：ChapterScript 提交时铸永久 beat id。
  - 应用 RecorderOutput：MemOp / ArcOp / WorldOp / TierNom。
  - 应用 SummaryDelta：SummaryStore 幂等 upsert（level,ref）。
  - 据 L1 建初始 ArcStore 台账（创世用）。
状态机守卫：非法转移直接 raise，fail-fast。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.primitives.enums import CharTier, WorldTier
from story_engine.primitives.ids import mint_beat, mint_memory_id
from story_engine.schemas.artifacts.recorder_output import (
    ArcOp,
    MemOp,
    RecorderOutput,
    TierNom,
    WorldOp,
)
from story_engine.schemas.stores.arc import ArcRecord, ArcTransition, Knowledge, ThreadAdvance
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.plan import L1
from story_engine.schemas.stores.script import ChapterScript
from story_engine.schemas.stores.summary import SummaryDelta, SummaryEntry
from story_engine.schemas.stores.world import WorldEntity, WorldKind, _PREFIX_KIND

# fs/秘密状态机：op → (合法前态集, 新态)
_FS_TRANS = {
    "PLANT": ({"PLANNED"}, "PLANTED"),
    "REINFORCE": ({"PLANTED", "REINFORCED"}, "REINFORCED"),
    "FULFILL": ({"PLANTED", "REINFORCED"}, "FULFILLED"),
}
_FS_TERMINAL = {"FULFILLED", "ABANDONED"}
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
    arc_transitions: list[tuple[str, str]] = field(default_factory=list)
    world_ops_applied: list[str] = field(default_factory=list)
    tier_noms_applied: list[str] = field(default_factory=list)
    summaries_upserted: list[str] = field(default_factory=list)
    noops: list[str] = field(default_factory=list)


class Applier:
    name = "applier"

    def __init__(self, embedder=None) -> None:
        self.embedder = embedder

    def _embed_text(self, text: str) -> list[float] | None:
        if self.embedder is None or not text:
            return None
        return self.embedder.embed([text])[0]

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
    def apply_recorder_output(
        self,
        ro: RecorderOutput,
        mem_store,
        arc_store,
        world_store=None,
        *,
        apply_tier_noms: bool = False,
    ) -> ApplyResult:
        """apply_tier_noms=False：提名只留档，等 Replanner 卷末确认后再落（默认）。
        True：立即落 MemoryEntry.tier（测试 / Replanner 确认后调用）。
        """
        result = ApplyResult()
        for op in ro.mem_ops:
            self._apply_mem_op(op, ro.chapter, mem_store, result)
        for op in ro.arc_ops:
            self._apply_arc_op(op, ro.chapter, arc_store, result)
        if world_store is not None:
            for op in ro.world_ops:
                self._apply_world_op(op, ro.chapter, world_store, result)
        for nom in ro.tier_noms:
            if apply_tier_noms:
                self._apply_tier_nom(nom, mem_store, result)
            else:
                result.noops.append(f"tier_nom:{nom.char}")  # 提名留档，未确认
        return result

    def apply_summary_delta(self, delta: SummaryDelta, summary_store) -> ApplyResult:
        """幂等 upsert：(level,ref) 已存在则替换。"""
        result = ApplyResult()
        for entry in delta.entries:
            entry.t_valid = entry.t_valid or delta.chapter
            entry.produced_by = delta.produced_by
            if entry.vec is None:
                entry.vec = self._embed_text(entry.text)
            key = entry.store_key
            existing = summary_store.get(key)
            if existing is None:
                summary_store.append(entry)
            else:
                summary_store.update(
                    key,
                    text=entry.text,
                    vec=entry.vec,
                    covers=entry.covers,
                    threads=entry.threads,
                    cast=entry.cast,
                    key_ops=entry.key_ops,
                    t_valid=entry.t_valid,
                    produced_by=entry.produced_by,
                    summarizer_version=entry.summarizer_version,
                )
            result.summaries_upserted.append(key)
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
                vec=self._embed_text(op.text or ""),
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

    # ── WorldOp ─────────────────────────────────────────────
    @staticmethod
    def _resolve_world_kind(op: WorldOp) -> WorldKind | None:
        """合法前缀 + 可选 kind → 落库 kind；非法（如 char.*）返回 None → 调用方 NOOP。"""
        prefix = op.entity_id.split(".", 1)[0] if "." in op.entity_id else ""
        from_prefix = _PREFIX_KIND.get(prefix)
        if from_prefix is None:
            return None
        if op.kind is None:
            return from_prefix
        if op.kind != from_prefix:
            return None
        return op.kind

    def _apply_world_op(self, op: WorldOp, chapter: int, world_store, result: ApplyResult) -> None:
        if op.op == "NOOP":
            result.noops.append(op.entity_id)
            return
        existing = world_store.get(op.entity_id)
        if op.op == "REGISTER":
            if existing is not None:
                result.noops.append(f"register_exists:{op.entity_id}")
                return
            kind = self._resolve_world_kind(op)
            if kind is None:
                # 角色等非 world 前缀、或 kind 与前缀冲突：降级 NOOP，不拖死整章
                result.noops.append(f"invalid_world_kind:{op.entity_id}:{op.kind}")
                return
            ent = WorldEntity(
                id=op.entity_id,
                canonical_name=op.canonical_name or op.entity_id.split(".", 1)[-1],
                aliases=list(op.aliases),
                kind=kind,
                tier=op.tier if isinstance(op.tier, WorldTier) else WorldTier(op.tier),
                origin="emergent",
                definition=op.definition,
                state=dict(op.state),
                t_valid=chapter,
                established_ch=chapter,
                evidence=list(op.evidence),
            )
            world_store.append(ent)
            result.world_ops_applied.append(op.entity_id)
        elif op.op == "UPDATE_STATE":
            if existing is None:
                raise ValueError(f"UPDATE_STATE 目标不存在: {op.entity_id}")
            merged = {**existing.state, **op.state}
            world_store.update(
                op.entity_id,
                state=merged,
                evidence=existing.evidence + list(op.evidence),
                version=existing.version + 1,
            )
            result.world_ops_applied.append(op.entity_id)
        elif op.op == "SOFT-INVALIDATE":
            if existing is None:
                raise ValueError(f"SOFT-INVALIDATE 目标不存在: {op.entity_id}")
            world_store.update(op.entity_id, t_invalid=chapter)
            result.world_ops_applied.append(op.entity_id)
        else:
            raise ValueError(f"未知 WorldOp: {op.op}")

    # ── TierNom ─────────────────────────────────────────────
    def _apply_tier_nom(self, nom: TierNom, mem_store, result: ApplyResult) -> None:
        """把 scope=char.* 的画像条目 tier 升到 to_tier（取 max，不降）。"""
        scope = nom.char if nom.char.startswith("char.") else f"char.{nom.char}"
        updated = 0
        for m in mem_store.query(scope=scope):
            current = int(m.tier) if m.tier is not None else 3
            if nom.to_tier < current:  # tier 数字越小越高
                mem_store.update(m.id, tier=CharTier(nom.to_tier))
                updated += 1
        result.tier_noms_applied.append(nom.char if updated else f"noop:{nom.char}")

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
