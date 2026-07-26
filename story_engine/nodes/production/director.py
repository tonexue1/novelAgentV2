"""Director —— setup（拆场定合同）+ dispatch（现场逐拍派工）。

对应 docs/nodes/production/director-setup.md / director-dispatch.md。

分权焊点：Director 只定**流向与锚**，内容 100% 归 Character；
schema 上 dramatic_goal / obligation.desc 只能是目标，禁台词。
"""

from __future__ import annotations

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.primitives.ids import mint_chapter, mint_scene
from story_engine.schemas.artifacts.chapter_plan import ChapterPlan
from story_engine.schemas.artifacts.scene_script import (
    BeatDispatch,
    SceneContract,
    SceneScript,
)
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.script import Beat
from story_engine.schemas.stores.world import WorldEntity

_SETUP_ROLE = "你是导演，负责把一章的粗桥段拆成若干**场景合同**。"
_SETUP_TASK = """把 ChapterPlan 拆成 2~4 个场景，每场出一份合同。

核心纪律——**定锚不定序**：
- 只定 obligations（本场必须命中的承重拍）和 exit_when（退出条件），
  **不要预先排 turn 顺序**，谁先说话是运行时涌现的。
- obligation.desc 写"张三逼李四摊牌身世"这种戏剧目标，**禁止写台词**。
- precede 只在真有因果先后时填，它是软约束。

硬要求（json 输出）：
- scene_id 形如 c{n}.s1、c{n}.s2，按顺序编号；obligation_id 形如 c{n}.s1.o1。
- location 必须是 loc.{slug}，且优先引用给定 canon 里已有的地点。
- cast 里的 char 用 char.{slug}，entry_state 写此人进场时的处境/情绪。
- budget.max_beats 给 6~12，防止场景跑不完。"""

_DISPATCH_ROLE = "你是现场调度，站在片场决定**下一拍谁来演、演什么目标**。"
_DISPATCH_TASK = """看本场合同和已经拍完的实录，决定下一步。

两种结果二选一：
1. 还没收场：给出下一拍的 owner + dramatic_goal（可带 hits 指向要命中的承重拍）。
2. 该收场了：close_scene=true。判据是承重拍已全部命中、且退出条件满足。

硬要求：
- dramatic_goal **只写目标**（如"逼他承认见过那把剑"），**绝不写台词原文**。
- owner 用 char.{slug}；环境事件用 ENV，旁白用 NARRATION（这两者不能有台词）。
- hits 必须是本场 obligations 里真实存在的 id，没有要命中的就留空。
- 优先推进尚未命中的承重拍，别原地打转。"""


class DirectorSetup:
    name = "director_setup"

    def split_scenes(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        plan: ChapterPlan,
        world: list[WorldEntity] | None = None,
        profiles: list[dict] | None = None,
    ) -> SceneScript:
        if ctx.llm is None:
            raise ValueError("DirectorSetup 需要 LLMClient")
        prompt = build_prompt(
            _SETUP_ROLE,
            _SETUP_TASK,
            [
                ("本章计划 ChapterPlan", as_json(plan)),
                ("可用 canon（地点/概念/势力，优先复用）", as_json(world or [], limit=2000)),
                ("出场人物粗画像", as_json(profiles or [], limit=1500)),
                ("本章章号", f"第 {chapter} 章"),
            ],
        )
        script = ctx.llm.complete_structured(prompt, SceneScript, node=self.name, chapter=chapter)
        return self._anchor(script, chapter=chapter, plan=plan)

    def _anchor(self, script: SceneScript, *, chapter: int, plan: ChapterPlan) -> SceneScript:
        """场景/承重拍 id 由系统重铸，保证位置 id 严格连号可寻址。"""
        ch = mint_chapter(chapter)
        script.chapter = ch
        script.derived_from = plan.chapter
        for m, scene in enumerate(script.scenes, start=1):
            old_scene_id = scene.scene_id
            scene.scene_id = mint_scene(ch, m)
            remap = {}
            for k, ob in enumerate(scene.obligations, start=1):
                remap[ob.obligation_id] = f"{scene.scene_id}.o{k}"
                ob.obligation_id = remap[ob.obligation_id]
            # precede 引用同场旧 id，跟着重映射；指不到的丢弃（软约束，不值得 fail）
            for ob in scene.obligations:
                ob.precede = [remap[p] for p in ob.precede if p in remap]
            if old_scene_id != scene.scene_id:
                for ob in scene.obligations:
                    ob.desc = ob.desc.replace(old_scene_id, scene.scene_id)
        return script


class DispatchDecision(SchemaModel):
    """dispatch 的一次决策：继续派工，或收场。"""

    close_scene: bool = False
    owner: str | None = None
    dramatic_goal: str | None = None
    hits: str | None = None
    directive: str | None = None
    reason: str | None = None


class DirectorDispatch:
    name = "director_dispatch"

    def next_beat(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        contract: SceneContract,
        done_beats: list[Beat],
    ) -> BeatDispatch | None:
        """返回下一拍派工；None = 收场。

        硬兜底优先于 LLM 判断：承重拍全命中或撞 budget，一律收场。
        """
        hit = {b.hits for b in done_beats if b.hits}
        pending = [o for o in contract.obligations if o.obligation_id not in hit]
        max_beats = contract.budget.max_beats
        if max_beats is not None and len(done_beats) >= max_beats:
            return None
        if not pending and done_beats:
            return None
        if ctx.llm is None:
            raise ValueError("DirectorDispatch 需要 LLMClient")

        decision = ctx.llm.complete_structured(
            build_prompt(
                _DISPATCH_ROLE,
                _DISPATCH_TASK,
                [
                    ("场景合同", as_json(contract)),
                    ("尚未命中的承重拍", as_json(pending)),
                    ("本场实录（已拍完的拍）", as_json(_recap(done_beats), limit=2500)),
                    ("上一拍的 handoff", as_json(done_beats[-1].handoff) if done_beats else "（开场）"),
                ],
            ),
            DispatchDecision,
            node=self.name,
            chapter=chapter,
        )
        if decision.close_scene or not decision.owner or not decision.dramatic_goal:
            return None
        valid_ids = {o.obligation_id for o in contract.obligations}
        return BeatDispatch(
            scene=contract.scene_id,
            owner=decision.owner,
            dramatic_goal=decision.dramatic_goal,
            hits=decision.hits if decision.hits in valid_ids else None,
            directive=decision.directive,
        )


def _recap(beats: list[Beat]) -> list[dict]:
    """本场实录的紧凑视图——dispatch 只需要知道谁做了什么、命中了哪个锚。"""
    return [
        {"owner": b.owner, "goal": b.dramatic_goal, "hits": b.hits, "text": b.as_text()}
        for b in beats
    ]
