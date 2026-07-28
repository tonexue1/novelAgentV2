"""Consistency Gate（一致性闸）—— 对应 docs/nodes/system/consistency-gate.md + ARCHITECTURE §3.5。

真相层守门人：串 hard-check → Continuity Critic → 按 severity 聚合决策 → 更新违规生命周期。
**没过闸的内容不许进 ScriptStore**，没有关闸开关。

两个检点，各自的最小修复范围：
  逐拍即时 → 只重调该拍（Character 逐拍生成，这是最便宜的投影）；
  场收束   → 同场重试 → 场重导(setup) → 整章重规划(planner) → 挂起。

降级：CORRECT 耗尽 = 接受最优候选 + 本章 flagged；BLOCK 爬满 = 该章不入库 + 呼人。
本节点只出决策，重新生成由编排（loop）执行——闸不碰生成器。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from story_engine.nodes.base import NodeContext
from story_engine.nodes.system.violation_log import ViolationTracker, worst_severity
from story_engine.nodes.validation.hard_check import check_beat, check_scene
from story_engine.primitives.enums import Severity
from story_engine.schemas.stores.violation import Violation

GateAction = Literal[
    "admit",           # 收下（flagged 时仍收，但章打标）
    "retry_beat",      # 只重调该拍
    "retry_scene",     # 同场重跑
    "redirect_scene",  # 场重导：Director·setup 重出该场合同
    "replan_chapter",  # 整章重规划：Planner 重来
    "escalate_volume", # 第④级：挂起本章 + 编排层调 Replanner
    "block",           # 兼容：等同 escalate_volume（爬满）
]


@dataclass
class GateDecision:
    action: GateAction
    violations: list[Violation] = field(default_factory=list)
    flagged: bool = False   # 降级放行：本章 consistency_status=flagged
    report: str = ""        # 结构化违规报告，喂给重试的生成器

    @property
    def admitted(self) -> bool:
        return self.action == "admit"


def format_violations(violations: list[Violation]) -> str:
    """违规报告：重试时原样喂给生成器，让它知道上一版错在哪。"""
    lines = []
    for v in violations:
        where = ""
        if v.locus is not None:
            where = v.locus.beat or v.locus.obligation or v.locus.scene or ""
        head = f"[{v.severity.value}/{v.category}]"
        tail = f"（建议：{v.suggestion}）" if v.suggestion else ""
        lines.append(f"- {head} {where} {v.message}{tail}".strip())
    return "\n".join(lines)


class ConsistencyGate:
    name = "consistency_gate"

    def __init__(
        self,
        tracker: ViolationTracker | None = None,
        *,
        retry_budget: int = 2,
        replan_budget: int = 1,
    ) -> None:
        self.tracker = tracker or ViolationTracker()
        self.retry_budget = retry_budget
        self.replan_budget = replan_budget
        self.flagged = False              # 本章是否已被降级放行过
        self._beat_attempts: dict[str, int] = {}
        self._scene_retries: dict[str, int] = {}
        self._scene_redirects: dict[str, int] = {}
        self._replans = 0

    # ── 检点①：逐拍即时 ─────────────────────────────────────
    def beat_gate(
        self,
        *,
        beat,
        contract,
        chapter: int,
        arc_store=None,
        world_ids: set[str] | None = None,
        mem_store=None,
    ) -> GateDecision:
        found = check_beat(
            beat,
            contract=contract,
            chapter=chapter,
            arc_store=arc_store,
            world_ids=world_ids,
            mem_store=mem_store,
        )
        vios = self.tracker.track(found)
        if not vios:
            self._settle_fixed(beat=beat.beat_id)
            return GateDecision("admit")

        worst = worst_severity(vios)
        if worst == Severity.ADVISORY:
            self.tracker.settle("advised", violations=vios)
            return GateDecision("admit", vios)

        key = beat.beat_id
        used = self._beat_attempts.get(key, 0)
        if used < self.retry_budget:
            self._beat_attempts[key] = used + 1
            self.tracker.note_attempt(
                level="beat", outcome="retry", violations=vios
            )
            return GateDecision("retry_beat", vios, report=format_violations(vios))

        if worst == Severity.BLOCK:
            # 这一拍怎么调都不对 → 投影到上一级，走场级阶梯（预算也归它管）
            return self._block_ladder(contract.scene_id, vios, format_violations(vios))

        # CORRECT 耗尽：接受最优候选，本章降级放行
        self.tracker.settle("flagged", violations=vios)
        self.flagged = True
        return GateDecision("admit", vios, flagged=True)

    # ── 检点②：场收束（硬检 + Critic）───────────────────────
    def scene_gate(
        self,
        ctx: NodeContext,
        *,
        scene,
        contract,
        chapter: int,
        arc_store=None,
        world_ids: set[str] | None = None,
        previous_scenes: list | None = None,
        critic=None,
        context=None,
        recent_summaries: list[str] | None = None,
    ) -> GateDecision:
        found = check_scene(
            scene,
            contract=contract,
            chapter=chapter,
            arc_store=arc_store,
            world_ids=world_ids,
            previous_scenes=previous_scenes,
        )
        if critic is not None:
            found += critic.review(
                ctx,
                chapter=chapter,
                scene=scene,
                contract=contract,
                context=context,
                recent_summaries=recent_summaries,
            )
        vios = self.tracker.track(found)
        sid = scene.scene_id
        if not vios:
            self._settle_fixed(scene=sid)
            return GateDecision("admit")

        worst = worst_severity(vios)
        if worst == Severity.ADVISORY:
            self.tracker.settle("advised", violations=vios)
            return GateDecision("admit", vios)

        report = format_violations(vios)
        if worst == Severity.BLOCK:
            return self._block_ladder(sid, vios, report)

        used = self._scene_retries.get(sid, 0)
        if used < self.retry_budget:
            self._scene_retries[sid] = used + 1
            self.tracker.note_attempt(level="scene", outcome="retry", violations=vios)
            return GateDecision("retry_scene", vios, report=report)

        # CORRECT 耗尽 → 接受最优候选 + flagged
        self.tracker.settle("flagged", violations=vios)
        self.flagged = True
        return GateDecision("admit", vios, flagged=True)

    def _block_ladder(self, sid: str, vios: list[Violation], report: str) -> GateDecision:
        used = self._scene_redirects.get(sid, 0)
        if used < self.retry_budget:
            self._scene_redirects[sid] = used + 1
            self.tracker.note_attempt(level="scene", outcome="redirect", violations=vios)
            return GateDecision("redirect_scene", vios, report=report)
        if self._replans < self.replan_budget:
            self._replans += 1
            self.tracker.note_attempt(level="chapter", outcome="replan", violations=vios)
            return GateDecision("replan_chapter", vios, report=report)
        # 第④级：挂起本章，编排层触发卷复盘
        self.tracker.note_attempt(level="volume", outcome="escalate", violations=vios)
        self.tracker.settle("blocked", violations=vios)
        return GateDecision("escalate_volume", vios, report=report)

    def reset_scene(self, scene_id: str) -> None:
        """场重来：拍级预算重新给（新合同下的拍是新的机会）。"""
        for key in [k for k in self._beat_attempts if k.startswith(f"{scene_id}.")]:
            del self._beat_attempts[key]

    # ── 章末 ────────────────────────────────────────────────
    def close_chapter(self) -> str:
        """结掉还开着的违规，返回本章 consistency_status。"""
        remaining = self.tracker.open_violations
        if remaining:
            worst = worst_severity(remaining)
            self.tracker.settle_remaining("flagged" if worst != Severity.ADVISORY else "advised")
            if worst != Severity.ADVISORY:
                self.flagged = True
        return "flagged" if self.flagged else "clean"

    def abort_chapter(self) -> None:
        """挂起收尾：还开着的违规一律记 blocked。"""
        self.tracker.settle_remaining("blocked")

    def _settle_fixed(self, *, scene: str | None = None, beat: str | None = None) -> None:
        stale = self.tracker.open_at(scene=scene, beat=beat)
        if stale:
            self.tracker.settle("fixed", violations=stale)
