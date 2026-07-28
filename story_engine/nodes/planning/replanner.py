"""Replanner —— 对应 docs/nodes/planning/replanner.md。

卷/篇末复盘：系统先算 DriftReport，再 LLM 决策 patch_l2 / revise_l1 / hold，
产 volume 摘要、loose-ends、确认 tier/emergent。
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.nodes.system.foreshadow import ForeshadowSignal, surface_foreshadows
from story_engine.primitives.enums import Importance
from story_engine.schemas.artifacts.recorder_output import TierNom
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.plan import L0, L1, L2
from story_engine.schemas.stores.summary import SummaryEntry

ReplannerAction = Literal["patch_l2", "revise_l1", "hold"]


class DriftReport(SchemaModel):
    thread_lag: float = 0.0
    foreshadow_overdue_rate: float = 0.0
    violation_density: float = 0.0
    goal_drift: float | None = None       # LLM 可填；系统侧可空
    notes: list[str] = Field(default_factory=list)


class LooseEnd(SchemaModel):
    id: str
    kind: Literal["foreshadow", "thread", "secret"] = "foreshadow"
    status: Literal["open", "overdue", "at_risk"] = "open"
    importance: Importance = Importance.MINOR
    recommendation: Literal["fulfill_in_next_vol", "reschedule", "abandon", "human"] = "fulfill_in_next_vol"
    reason: str = ""


class WorldPromote(SchemaModel):
    entity_id: str
    to_tier: Literal["core", "major", "minor"] = "major"


class ReplannerOutput(SchemaModel):
    drift_report: DriftReport = Field(default_factory=DriftReport)
    action: ReplannerAction = "hold"
    l2_next: L2 | None = None
    l1_revision: L1 | None = None
    volume_summary: SummaryEntry | None = None
    saga_summary: SummaryEntry | None = None
    loose_ends: list[LooseEnd] = Field(default_factory=list)
    confirmed_tiers: list[TierNom] = Field(default_factory=list)
    confirmed_emergent: list[str] = Field(default_factory=list)
    world_promote: list[WorldPromote] = Field(default_factory=list)
    human_gate: str | None = None


_ROLE = "你是卷复盘师，诊断本卷实际相对意图的漂移，并决定如何修正。"
_TASK = """根据 DriftReport 与台账，输出复盘决策。

硬要求：
- action 只能是 hold / patch_l2 / revise_l1。
- core 伏笔逾期必须 human_gate 非空，不许自动废。
- volume_summary：level=volume，ref=卷 id，text 2~5 句梗概。
- loose_ends：所有未收束伏笔/主线。
- confirmed_tiers：只确认值得晋升的提名。
- 默认倾向 patch_l2；只有里程碑不可达才 revise_l1。"""


def compute_drift(
    *,
    l1: L1,
    l2: L2 | None,
    arc_store,
    chapter: int,
    violations_in_volume: int = 0,
    chapters_in_volume: int = 1,
    volume_end_ch: int | None = None,
) -> DriftReport:
    """确定性预计算漂移指标。"""
    signals = surface_foreshadows(
        arc_store, chapter, l2=l2, volume_end_ch=volume_end_ch,
    )
    active = [
        r for r in arc_store.all()
        if r.kind == "foreshadow" and r.state not in {"FULFILLED", "ABANDONED"}
    ]
    overdue = [s for s in signals if s.status == "overdue"]
    overdue_rate = (len(overdue) / len(active)) if active else 0.0

    # thread_lag：有 advances 的 thread，末次 advance 章 vs 卷末的距离粗估
    lags: list[float] = []
    for t in l1.threads:
        rec = arc_store.get(t.thread_id)
        if rec is None or not rec.advances:
            lags.append(float(max(0, (volume_end_ch or chapter) - chapter)))
            continue
        last = max(a.ch for a in rec.advances)
        lags.append(float(max(0, chapter - last)))
    thread_lag = sum(lags) / len(lags) if lags else 0.0

    density = violations_in_volume / max(1, chapters_in_volume)
    notes: list[str] = []
    if overdue_rate >= 0.3:
        notes.append(f"伏笔逾期率 {overdue_rate:.2f}")
    if thread_lag > 2:
        notes.append(f"主线滞后 {thread_lag:.1f} 章")
    if any(s.is_core_overdue for s in signals):
        notes.append("存在 core 伏笔逾期")
    return DriftReport(
        thread_lag=round(thread_lag, 2),
        foreshadow_overdue_rate=round(overdue_rate, 3),
        violation_density=round(density, 2),
        notes=notes,
    )


def decide_action(drift: DriftReport, signals: list[ForeshadowSignal]) -> ReplannerAction:
    """确定性默认动作（LLM 可覆盖，但 core 逾期强制 human）。"""
    if any(s.is_core_overdue for s in signals):
        return "revise_l1"  # 伴随 human_gate
    if drift.thread_lag > 2 or drift.foreshadow_overdue_rate >= 0.3:
        return "patch_l2"
    if drift.thread_lag <= 2 and drift.foreshadow_overdue_rate < 0.3:
        return "hold"
    return "patch_l2"


class Replanner:
    name = "replanner"

    def review(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        vol_id: str,
        l0: L0,
        l1: L1,
        l2: L2 | None = None,
        arc_store=None,
        mem_store=None,
        tier_noms: list[TierNom] | None = None,
        violations_in_volume: int = 0,
        chapters_in_volume: int = 1,
        volume_end_ch: int | None = None,
    ) -> ReplannerOutput:
        if ctx.llm is None:
            raise ValueError("Replanner 需要 LLMClient")
        signals = surface_foreshadows(
            arc_store, chapter, l2=l2, volume_end_ch=volume_end_ch,
        )
        drift = compute_drift(
            l1=l1, l2=l2, arc_store=arc_store, chapter=chapter,
            violations_in_volume=violations_in_volume,
            chapters_in_volume=chapters_in_volume,
            volume_end_ch=volume_end_ch,
        )
        default_action = decide_action(drift, signals)
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("立意 L0", as_json(l0, limit=800)),
                ("意图 L1", as_json(l1, limit=2500)),
                ("本卷 L2", as_json(l2, limit=2000) if l2 else ""),
                ("DriftReport（系统预计算）", as_json(drift)),
                ("伏笔信号", as_json([
                    {
                        "arc_id": s.arc_id,
                        "status": s.status,
                        "importance": s.importance.value if hasattr(s.importance, "value") else s.importance,
                        "deadline_ch": s.deadline_ch,
                        "desc": s.desc,
                    }
                    for s in signals
                ])),
                ("待确认 tier_noms", as_json(tier_noms or [])),
                ("默认建议动作", default_action),
                ("卷 id / 末章", f"vol_id={vol_id} chapter={chapter}"),
            ],
        )
        out = ctx.llm.complete_structured(
            prompt, ReplannerOutput, node=self.name, chapter=chapter, temperature=0
        )
        # 系统侧守卫：合并预计算 drift；core 逾期强制 human_gate
        out.drift_report = drift
        if any(s.is_core_overdue for s in signals):
            out.human_gate = out.human_gate or "core 伏笔逾期，须人工决策，禁止自动废弃"
            if out.action == "hold":
                out.action = "revise_l1"
        if out.volume_summary is None:
            out.volume_summary = SummaryEntry(
                level="volume",
                ref=vol_id,
                text=f"{vol_id} 复盘摘要（自动兜底）",
                t_valid=chapter,
                produced_by="Replanner",
                summarizer_version="m4b.1",
            )
        else:
            out.volume_summary = out.volume_summary.model_copy(update={
                "level": "volume",
                "ref": vol_id,
                "t_valid": chapter,
                "produced_by": "Replanner",
            })
        return out
