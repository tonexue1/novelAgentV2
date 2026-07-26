"""单章递推循环 —— 对应受控递推 xᵢ=f(R(Sᵢ₋₁)); Sᵢ=U(Sᵢ₋₁,xᵢ)。

M2 垂直切片，一章的全程：
  Planner → Director·setup → (dispatch ⇄ Character)* → ChapterScript
    → Applier 定序落库 → Writer 渲染散文
    → Extractor → Faithfulness → Reconciler → Applier 应用增量

尚未接（M3）：一致性闸全链、Continuity Critic、升级阶梯、真检索装配。
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
from story_engine.nodes.system.applier import Applier
from story_engine.nodes.validation.faithfulness_check import FaithfulnessCheck
from story_engine.primitives.ids import mint_chapter
from story_engine.schemas.artifacts.chapter_plan import ChapterPlan
from story_engine.schemas.artifacts.scene_script import SceneScript
from story_engine.schemas.stores.manuscript import Manuscript
from story_engine.schemas.stores.plan import L0, L1, L2
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene, SceneCast
from story_engine.schemas.stores.world import WorldEntity

# 单场最多拍数的兜底（合同没给 budget 时用），防 dispatch 不收场
_DEFAULT_MAX_BEATS = 12


@dataclass
class ChapterResult:
    chapter: str
    plan: ChapterPlan | None = None
    scene_script: SceneScript | None = None
    script: ChapterScript | None = None
    manuscript: Manuscript | None = None
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
) -> ChapterResult:
    """跑完第 n 章。stores 需含 script / mem / arc；manuscript 可选。

    skip_writer=True 时跳过散文渲染（走查/批跑常用；Recorder 只吃 Script）。
    """
    stores = stores or ctx.stores
    chapter_id = mint_chapter(n)
    trace: list[str] = []
    ctx.chapter = n

    script_store = stores["script"]
    mem_store = stores["mem"]
    arc_store = stores["arc"]
    manuscript_store = stores.get("manuscript")
    applier = Applier()

    # ── 1. 规划：L2 → L3 ────────────────────────────────────────
    plan = Planner().plan(
        ctx,
        chapter=n,
        l0=l0,
        l1=l1,
        l2=l2,
        arcs=arc_store.all(),
        due_foreshadows=_due_foreshadows(arc_store, n),
        recent_summaries=_recent_tails(script_store, n),
    )
    trace.append(f"{chapter_id}: plan ({len(plan.story_beats)} 桥段)")

    # ── 2. 拆场：L3 → 场景合同 ──────────────────────────────────
    scene_script = DirectorSetup().split_scenes(ctx, chapter=n, plan=plan, world=world)
    trace.append(f"{chapter_id}: setup ({len(scene_script.scenes)} 场)")

    # ── 3. 逐场：dispatch ⇄ Character 涌现 beats ─────────────────
    dispatcher, actor = DirectorDispatch(), Character()
    scenes: list[Scene] = []
    for contract in scene_script.scenes:
        buffer: list[Beat] = []
        limit = contract.budget.max_beats or _DEFAULT_MAX_BEATS
        while len(buffer) < limit:
            dispatch = dispatcher.next_beat(
                ctx, chapter=n, contract=contract, done_beats=buffer
            )
            if dispatch is None:
                break
            buffer.append(
                actor.act(
                    ctx,
                    chapter=n,
                    dispatch=dispatch,
                    contract=contract,
                    known_facts=_known_facts(mem_store, dispatch.owner, n),
                    buffer=buffer,
                )
            )
        scenes.append(_to_scene(contract, buffer))
        trace.append(f"{chapter_id}: {contract.scene_id} 收场（{len(buffer)} 拍）")

    # ── 4. 落库主真相 ────────────────────────────────────────────
    # 一致性闸要 M3 才接。在那之前本章并未过闸，只能标 flagged（"是真相，
    # 但可能有轻微问题"）——标成 clean 等于给没安检的货盖合格章。
    script = ChapterScript(
        chapter=chapter_id,
        volume=plan.derived_from.l2_vol_id,
        theme=plan.theme,
        tone=plan.tone,
        covered_threads=[t.thread_id for t in plan.thread_advances],
        consistency_status="flagged",
        derived_from=plan.chapter,
        scenes=scenes,
    )
    applier.assign_beat_ids(script)
    script_store.append(script)
    trace.append(f"{chapter_id}: script 落库")

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
        arcs=arc_store.all(),
    )
    applier.apply_recorder_output(reconciled.output, mem_store, arc_store)
    trace.append(f"{chapter_id}: 对账落库（降级 {len(reconciled.coerced)} 条）")

    return ChapterResult(
        chapter=chapter_id,
        plan=plan,
        scene_script=scene_script,
        script=script,
        manuscript=manuscript,
        rejected=verified.rejected,
        coerced=reconciled.coerced,
        trace=trace,
    )


# ── 上下文装配（M2 糙版；M3 换成 Retriever + Assembler 按节点画像）──


def _to_scene(contract, beats: list[Beat]) -> Scene:
    return Scene(
        scene_id=contract.scene_id,
        location=contract.location,
        pov=contract.pov,
        goal=contract.goal,
        conflict=contract.conflict,
        contract_ref=contract.scene_id,
        time=contract.time,
        cast=[SceneCast(char=c.char, entry_state=c.entry_state) for c in contract.cast],
        beats=beats,
    )


def _due_foreshadows(arc_store, chapter: int) -> list[str]:
    """到期未收的伏笔——Planner 的首要义务。"""
    due: list[str] = []
    for rec in arc_store.all():
        if rec.kind != "foreshadow" or rec.state in {"FULFILLED", "ABANDONED"}:
            continue
        deadline = rec.payoff_deadline
        if deadline and deadline.granularity == "chapter":
            try:
                if chapter >= int(str(deadline.ref).lstrip("c")):
                    due.append(rec.id)
            except ValueError:
                continue
    return due


def _recent_tails(script_store, chapter: int, k: int = 2) -> list[str]:
    """最近 k 章的尾段——M2 没有 Summarizer，先用原文末尾顶上。"""
    out: list[str] = []
    for i in range(max(1, chapter - k), chapter):
        script = script_store.get(mint_chapter(i))
        if script is None:
            continue
        beats = [b.as_text() for s in script.scenes for b in s.beats]
        out.append(f"c{i}: " + " / ".join(beats[-4:]))
    return out


def _previous_tail(manuscript_store, chapter: int) -> str | None:
    if manuscript_store is None or chapter <= 1:
        return None
    prev = manuscript_store.get(mint_chapter(chapter - 1))
    return prev.text if prev else None


def _known_facts(mem_store, owner: str, chapter: int, k: int = 12) -> list[str]:
    """该角色 as-of 已知的事——认知边界的粗版实现。"""
    if owner in {"ENV", "NARRATION"}:
        return []
    items = [m for m in mem_store.as_of(chapter) if m.scope == owner]
    return [m.text for m in items[-k:]]


def _brief_memories(mem_store, chapter: int, k: int = 20) -> list[dict]:
    return [
        {"id": m.id, "type": m.type, "scope": m.scope, "text": m.text}
        for m in mem_store.as_of(chapter)[-k:]
    ]


def _related_memories(mem_store, chapter: int, k: int = 30) -> list:
    """对账的候选池。M3 换成按 scope/语义检索，M2 先给 as-of 全量尾部。"""
    return mem_store.as_of(chapter)[-k:]
