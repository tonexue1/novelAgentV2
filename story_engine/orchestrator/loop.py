"""单章递推循环 —— 对应受控递推 xᵢ=f(R(Sᵢ₋₁)); Sᵢ=U(Sᵢ₋₁,xᵢ)。

M3 垂直切片，一章的全程：
  Planner → Director·setup → (dispatch ⇄ Character → 逐拍硬检)* → 场收束
    → [一致性闸: 场级硬检 + Continuity Critic] → 过闸才拼进 staged 章
    → 章末一次性落库（clean | flagged）→ Writer 渲染散文
    → Extractor → Faithfulness → Reconciler → Applier 应用增量

守门纪律：**没过闸的内容不许进 ScriptStore**。本章生成期间内容都在 StagedScriptView 里，
BLOCK 爬满阶梯则该章完全不入库（挂起），Recorder 不跑。

尚未接（M4b）：Replanner 卷复盘（阶梯第四级）、向量检索。
本文件只负责编排与工作缓冲，所有语义判断都在节点里。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.consumption.writer import Writer
from story_engine.nodes.planning.planner import Planner
from story_engine.nodes.production.character import Character
from story_engine.nodes.production.director import DirectorDispatch, DirectorSetup
from story_engine.nodes.recorder.extractor import Extractor
from story_engine.nodes.recorder.reconciler import Reconciler
from story_engine.nodes.recorder.summarizer import Summarizer
from story_engine.nodes.system.applier import Applier
from story_engine.nodes.system.assembler import Assembler
from story_engine.nodes.system.consistency_gate import ConsistencyGate, GateDecision
from story_engine.nodes.system.embedder import build_embedder
from story_engine.nodes.system.foreshadow import core_overdue, surface_foreshadows
from story_engine.nodes.system.violation_log import ViolationTracker
from story_engine.nodes.validation.continuity_critic import ContinuityCritic
from story_engine.nodes.validation.faithfulness_check import FaithfulnessCheck
from story_engine.orchestrator.staged import StagedScriptView
from story_engine.primitives.ids import mint_chapter
from story_engine.schemas.artifacts.chapter_plan import ChapterPlan
from story_engine.schemas.artifacts.recorder_output import TierNom
from story_engine.schemas.artifacts.scene_script import BeatDispatch, SceneScript
from story_engine.schemas.stores.manuscript import Manuscript
from story_engine.schemas.stores.plan import L0, L1, L2
from story_engine.schemas.stores.script import ChapterScript, Scene, SceneCast
from story_engine.schemas.stores.summary import SummaryDelta
from story_engine.schemas.stores.violation import Violation
from story_engine.schemas.stores.world import WorldEntity
from story_engine.nodes.planning.replanner import Replanner, ReplannerOutput

# 单场最多拍数的兜底（合同没给 budget 时用），防 dispatch 不收场
_DEFAULT_MAX_BEATS = 12


@dataclass
class ChapterResult:
    chapter: str
    plan: ChapterPlan | None = None
    scene_script: SceneScript | None = None
    script: ChapterScript | None = None
    manuscript: Manuscript | None = None
    consistency_status: str | None = None                   # clean | flagged；挂起为 None
    blocked: bool = False                                   # 爬满阶梯仍不过，该章未入库
    violations: list[Violation] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)      # 忠实性校验拒掉的候选
    coerced: list[dict] = field(default_factory=list)       # 对账被系统降级的 op
    trace: list[str] = field(default_factory=list)


def run_chapter(
    ctx: NodeContext,
    n: int,
    *,
    l0: L0,
    l1: L1,
    l2: L2 | None = None,
    world: list[WorldEntity] | None = None,
    stores: dict | None = None,
    style: str | None = None,
    skip_writer: bool = False,
    enable_critic: bool = True,
) -> ChapterResult:
    """跑完第 n 章。stores 需含 script / mem / arc；manuscript / violation / world / summary 可选。

    skip_writer=True 时跳过散文渲染（走查/批跑常用；Recorder 只吃 Script）。
    enable_critic=False 时场收束只跑硬检（走查加速；正品默认开）。
    """
    stores = stores or ctx.stores
    chapter_id = mint_chapter(n)
    trace: list[str] = []
    ctx.chapter = n

    script_store = stores["script"]
    mem_store = stores["mem"]
    arc_store = stores["arc"]
    manuscript_store = stores.get("manuscript")
    world_store = stores.get("world")
    summary_store = stores.get("summary")
    # Director/硬检仍吃 list；优先用 JsonStore 快照
    if world is None and world_store is not None:
        world = world_store.as_of(n) if hasattr(world_store, "as_of") else world_store.all()
    # world_ids 对照真相取自 live WorldStore（含已入库涌现实体），与喂给 Director
    # 的种子 world 列表解耦——否则运行期吸收的涌现地点对硬检不可见，后续章会误报。
    if world_store is not None and hasattr(world_store, "as_of"):
        world_ids = {w.id for w in world_store.as_of(n)}
    elif world:
        world_ids = {w.id for w in world}
    else:
        world_ids = None

    gate = ConsistencyGate(ViolationTracker(stores.get("violation")))
    assembler = Assembler()
    critic: ContinuityCritic | None = ContinuityCritic() if enable_critic else None
    # Embedder：默认 fake；ctx 可注入
    embedder = getattr(ctx, "embedder", None) or build_embedder()
    applier = Applier(embedder=embedder)

    plan: ChapterPlan | None = None
    scene_script: SceneScript | None = None
    staged: StagedScriptView | None = None
    replan_report = ""
    volume_end = _volume_end_ch(l2)

    # core 逾期：章初即标，供 Planner 强提示；Gate 侧在章末 escalate
    fs_signals = surface_foreshadows(
        arc_store, n, l2=l2, volume_end_ch=volume_end,
    )
    due_ids = [s.arc_id for s in fs_signals]

    # ── 1~3. 规划 → 拆场 → 逐场过闸（BLOCK 可整章重来一次）──────
    while True:
        plan = Planner().plan(
            ctx,
            chapter=n,
            l0=l0,
            l1=l1,
            l2=l2,
            arcs=arc_store.all(),
            due_foreshadows=due_ids,
            recent_summaries=_recent_summaries(summary_store, script_store, n),
            retrieved=assembler.assemble(
                node="planner", chapter=n, mem_store=mem_store, arc_store=arc_store,
                focus=_plan_focus(l2, n),
            ).facts(),
            violations=replan_report or None,
        )
        trace.append(f"{chapter_id}: plan ({len(plan.story_beats)} 桥段)")

        scene_script = DirectorSetup().split_scenes(
            ctx, chapter=n, plan=plan, world=world, violations=replan_report or None
        )
        trace.append(f"{chapter_id}: setup ({len(scene_script.scenes)} 场)")

        staged = StagedScriptView(script_store, _skeleton(chapter_id, plan))
        verdict = _run_scenes(
            ctx, n,
            plan=plan, scene_script=scene_script, staged=staged, gate=gate,
            assembler=assembler, critic=critic, world=world, world_ids=world_ids,
            mem_store=mem_store, arc_store=arc_store, script_store=script_store,
            summary_store=summary_store, trace=trace,
        )
        if verdict.action == "replan_chapter":
            replan_report = verdict.report
            trace.append(f"{chapter_id}: BLOCK 升级 → 整章重规划")
            continue
        if verdict.action in ("block", "escalate_volume"):
            gate.abort_chapter()
            need_volume = verdict.action == "escalate_volume" or bool(core_overdue(fs_signals))
            trace.append(
                f"{chapter_id}: 爬满阶梯仍未过闸 → 挂起"
                + ("（升级卷复盘）" if need_volume else "")
            )
            return ChapterResult(
                chapter=chapter_id, plan=plan, scene_script=scene_script,
                blocked=True, violations=gate.tracker.settled, trace=trace,
            )
        break

    # ── 4. 过闸后落库主真相 ──────────────────────────────────────
    status = gate.close_chapter()
    script = staged.commit(consistency_status=status)
    trace.append(f"{chapter_id}: 过闸落库（{status}）")

    # ── 5. 消费层渲染（读 Script，不回写真相层）─────────────────
    manuscript: Manuscript | None = None
    if not skip_writer:
        manuscript = Writer().render(
            ctx, chapter=n, script=script, style=style,
            previous_tail=_previous_tail(manuscript_store, n),
        )
        if manuscript_store is not None:
            manuscript_store.append(manuscript)
        trace.append(f"{chapter_id}: 散文 {len(manuscript.text)} 字")
    else:
        trace.append(f"{chapter_id}: 跳过 Writer")

    # ── 6. Recorder：抽取 → 忠实性 → 对账 → 落库 ────────────────
    candidates = Extractor().extract(
        ctx, chapter=n, script=script,
        related_memories=_brief_memories(mem_store, n),
        arcs=list(arc_store.all()),
    )
    verified = FaithfulnessCheck().verify(
        ctx, chapter=n, candidates=candidates, script_store=script_store
    )
    trace.append(
        f"{chapter_id}: 抽取 {len(candidates.mem_ops)} 条，"
        f"校验拒 {verified.reject_count} 条"
    )
    reconciled = Reconciler().reconcile(
        ctx, chapter=n, candidates=verified.passed,
        related=_related_memories(mem_store, n),
        arcs=list(arc_store.all()),
        worlds=list(world_store.all()) if world_store is not None else [],
    )
    applier.apply_recorder_output(
        reconciled.output, mem_store, arc_store, world_store=world_store,
    )
    trace.append(f"{chapter_id}: 对账落库（降级 {len(reconciled.coerced)} 条）")

    # ── 7. Summarizer：多分辨率摘要（独立 SummaryDelta）──────────
    if summary_store is not None:
        delta = Summarizer().summarize(ctx, chapter=n, script=script)
        applied = applier.apply_summary_delta(delta, summary_store)
        trace.append(f"{chapter_id}: 摘要 {len(applied.summaries_upserted)} 条")

    return ChapterResult(
        chapter=chapter_id,
        plan=plan,
        scene_script=scene_script,
        script=script,
        manuscript=manuscript,
        consistency_status=status,
        violations=gate.tracker.settled,
        rejected=verified.rejected,
        coerced=reconciled.coerced,
        trace=trace,
    )


# ── 逐场：dispatch ⇄ Character → 逐拍硬检 → 场收束过闸 ────────


def _run_scenes(
    ctx: NodeContext,
    n: int,
    *,
    plan: ChapterPlan,
    scene_script: SceneScript,
    staged: StagedScriptView,
    gate: ConsistencyGate,
    assembler: Assembler,
    critic: ContinuityCritic | None,
    world,
    world_ids,
    mem_store,
    arc_store,
    script_store,
    summary_store,
    trace: list[str],
) -> GateDecision:
    """跑完本章所有场。返回 admit（全过）或需要整章升级的决策。"""
    chapter_id = mint_chapter(n)
    for index, _ in enumerate(scene_script.scenes):
        report = ""
        while True:
            contract = scene_script.scenes[index]
            gate.reset_scene(contract.scene_id)
            staged.open_scene(_scene_shell(contract))
            decision = _run_scene(
                ctx, n,
                contract=contract, staged=staged, gate=gate, assembler=assembler,
                critic=critic, world_ids=world_ids, mem_store=mem_store,
                arc_store=arc_store, script_store=script_store,
                summary_store=summary_store, report=report,
            )
            if decision.admitted:
                staged.admit_scene()
                flag = "（flagged）" if decision.flagged else ""
                trace.append(
                    f"{chapter_id}: {contract.scene_id} 过闸{flag}"
                    f"（{len(staged.admitted_scenes[-1].beats)} 拍）"
                )
                break

            staged.discard_draft()
            report = decision.report
            if decision.action == "retry_scene":
                trace.append(f"{chapter_id}: {contract.scene_id} 同场重试")
                continue
            if decision.action == "redirect_scene":
                trace.append(f"{chapter_id}: {contract.scene_id} 场重导")
                scene_script.scenes[index] = DirectorSetup().redirect(
                    ctx, chapter=n, plan=plan, contract=contract,
                    violations=report, world=world,
                )
                continue
            return decision  # replan_chapter / block：交回章级
    return GateDecision("admit")


def _run_scene(
    ctx: NodeContext,
    n: int,
    *,
    contract,
    staged: StagedScriptView,
    gate: ConsistencyGate,
    assembler: Assembler,
    critic: ContinuityCritic | None,
    world_ids,
    mem_store,
    arc_store,
    script_store,
    summary_store,
    report: str,
) -> GateDecision:
    """演完一场（逐拍即时硬检），再整场过闸。"""
    dispatcher = DirectorDispatch()
    limit = contract.budget.max_beats or _DEFAULT_MAX_BEATS

    while len(staged.draft_scene.beats) < limit:
        dispatch = dispatcher.next_beat(
            ctx, chapter=n, contract=contract, done_beats=staged.draft_scene.beats
        )
        if dispatch is None:
            break
        decision = _run_beat(
            ctx, n,
            dispatch=dispatch, contract=contract, staged=staged, gate=gate,
            assembler=assembler, world_ids=world_ids, mem_store=mem_store,
            arc_store=arc_store, scene_report=report,
        )
        if not decision.admitted:
            return decision  # 拍级升级：整场重来/重导

    critic_ctx = None
    if critic is not None:
        critic_ctx = assembler.assemble(
            node="continuity-critic", chapter=n, mem_store=mem_store,
            arc_store=arc_store, focus=contract.goal,
            cast=[c.char for c in contract.cast],
        )
    return gate.scene_gate(
        ctx,
        scene=staged.draft_scene,
        contract=contract,
        chapter=n,
        arc_store=arc_store,
        world_ids=world_ids,
        previous_scenes=staged.admitted_scenes,
        critic=critic,
        context=critic_ctx,
        recent_summaries=_recent_summaries(summary_store, script_store, n),
    )


def _run_beat(
    ctx: NodeContext,
    n: int,
    *,
    dispatch: BeatDispatch,
    contract,
    staged: StagedScriptView,
    gate: ConsistencyGate,
    assembler: Assembler,
    world_ids,
    mem_store,
    arc_store,
    scene_report: str,
) -> GateDecision:
    """演一拍 + 逐拍即时硬检。违规先只重调这一拍。"""
    known_facts = assembler.known_facts(
        char=dispatch.owner, chapter=n, mem_store=mem_store,
        arc_store=arc_store, focus=dispatch.dramatic_goal,
    )
    report = scene_report
    while True:
        beat = staged.stage_beat(
            Character().act(
                ctx,
                chapter=n,
                dispatch=_with_report(dispatch, report),
                contract=contract,
                known_facts=known_facts,
                buffer=staged.draft_scene.beats,
            )
        )
        decision = gate.beat_gate(
            beat=beat, contract=contract, chapter=n,
            arc_store=arc_store, world_ids=world_ids, mem_store=mem_store,
        )
        if decision.admitted:
            return decision
        staged.drop_last_beat()
        if decision.action != "retry_beat":
            return decision
        report = decision.report


def _with_report(dispatch: BeatDispatch, report: str) -> BeatDispatch:
    if not report:
        return dispatch
    directive = (dispatch.directive or "").strip()
    note = f"【上一版这一拍被一致性闸拦下，必须改掉】\n{report}"
    return dispatch.model_copy(update={"directive": f"{directive}\n{note}".strip()})


# ── 装配与派生（检索交 Assembler，这里只留纯结构性的取数）──────


def _skeleton(chapter_id: str, plan: ChapterPlan) -> ChapterScript:
    """章头。scenes 逐场过闸后才填，consistency_status 章末才定。"""
    return ChapterScript(
        chapter=chapter_id,
        volume=plan.derived_from.l2_vol_id,
        theme=plan.theme,
        tone=plan.tone,
        covered_threads=[t.thread_id for t in plan.thread_advances],
        derived_from=plan.chapter,
        scenes=[],
    )


def _scene_shell(contract) -> Scene:
    """空场壳：场头来自合同，拍由 Character 逐个填进 staged 缓冲。"""
    return _to_scene(contract, [])


def _to_scene(contract, beats) -> Scene:
    """合同 + 拍列表 → Scene（walk 分步脚本与 staged 共用）。"""
    return Scene(
        scene_id=contract.scene_id,
        location=contract.location,
        pov=contract.pov,
        goal=contract.goal,
        conflict=contract.conflict,
        contract_ref=contract.scene_id,
        time=contract.time,
        cast=[SceneCast(char=c.char, entry_state=c.entry_state) for c in contract.cast],
        beats=list(beats),
    )


def _plan_focus(l2: L2 | None, chapter: int) -> str:
    if l2 is None:
        return ""
    for b in l2.chapter_beats:
        if b.planned_seq == chapter:
            return b.event
    return l2.goal or ""


def _volume_end_ch(l2: L2 | None) -> int | None:
    if l2 is None or not l2.chapter_beats:
        return None
    return max(b.planned_seq for b in l2.chapter_beats)


def _due_foreshadows(arc_store, chapter: int) -> list[str]:
    """兼容旧调用：仅章粒度。"""
    return [s.arc_id for s in surface_foreshadows(arc_store, chapter)]


def run_volume_review(
    ctx: NodeContext,
    *,
    chapter: int,
    vol_id: str,
    l0: L0,
    l1: L1,
    l2: L2 | None = None,
    stores: dict | None = None,
    tier_noms: list[TierNom] | None = None,
    violations_in_volume: int = 0,
    chapters_in_volume: int = 1,
) -> ReplannerOutput:
    """卷末复盘入口：Replanner → 落 volume 摘要 → 确认 tier_noms。"""
    stores = stores or ctx.stores
    arc_store = stores["arc"]
    mem_store = stores["mem"]
    summary_store = stores.get("summary")
    volume_end = _volume_end_ch(l2) or chapter
    embedder = getattr(ctx, "embedder", None) or build_embedder()
    applier = Applier(embedder=embedder)

    out = Replanner().review(
        ctx,
        chapter=chapter,
        vol_id=vol_id,
        l0=l0,
        l1=l1,
        l2=l2,
        arc_store=arc_store,
        mem_store=mem_store,
        tier_noms=tier_noms,
        violations_in_volume=violations_in_volume,
        chapters_in_volume=chapters_in_volume,
        volume_end_ch=volume_end,
    )
    if summary_store is not None and out.volume_summary is not None:
        applier.apply_summary_delta(
            SummaryDelta(chapter=chapter, entries=[out.volume_summary], produced_by="Replanner"),
            summary_store,
        )
        if out.saga_summary is not None:
            applier.apply_summary_delta(
                SummaryDelta(chapter=chapter, entries=[out.saga_summary], produced_by="Replanner"),
                summary_store,
            )
    if out.confirmed_tiers:
        from story_engine.schemas.artifacts.recorder_output import RecorderOutput

        applier.apply_recorder_output(
            RecorderOutput(chapter=chapter, tier_noms=out.confirmed_tiers),
            mem_store, arc_store, apply_tier_noms=True,
        )
    return out


def _recent_summaries(summary_store, script_store, chapter: int, k: int = 2) -> list[str]:
    """近段上下文：优先读 SummaryStore 章摘要；无则回退原文尾段。"""
    out: list[str] = []
    for i in range(max(1, chapter - k), chapter):
        ref = mint_chapter(i)
        if summary_store is not None:
            entry = summary_store.get(f"chapter:{ref}")
            if entry is not None:
                out.append(f"{ref}: {entry.text}")
                continue
        script = script_store.get(ref)
        if script is None:
            continue
        beats = [b.as_text() for s in script.scenes for b in s.beats]
        out.append(f"{ref}: " + " / ".join(beats[-4:]))
    return out


def _recent_tails(script_store, chapter: int, k: int = 2) -> list[str]:
    """兼容旧调用：无 summary_store 时的原文尾段。"""
    return _recent_summaries(None, script_store, chapter, k=k)


def _previous_tail(manuscript_store, chapter: int) -> str | None:
    if manuscript_store is None or chapter <= 1:
        return None
    prev = manuscript_store.get(mint_chapter(chapter - 1))
    return prev.text if prev else None


def _brief_memories(mem_store, chapter: int, k: int = 20) -> list[dict]:
    return [
        {"id": m.id, "type": m.type, "scope": m.scope, "text": m.text}
        for m in mem_store.as_of(chapter)[-k:]
    ]


def _related_memories(mem_store, chapter: int, k: int = 30) -> list:
    """对账的候选池。M4 换成按 scope/语义检索，先给 as-of 全量尾部。"""
    return mem_store.as_of(chapter)[-k:]
