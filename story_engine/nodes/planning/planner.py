"""Planner —— 对应 docs/nodes/planning/planner.md。

每章开头：读 P(L0/L1/L2) + Arc 进度 + 到期伏笔 + 近章摘要 → ChapterPlan(L3)。
**只到章级义务，不映射到场**（拆场是 Director 的活）。
chapter / derived_from 是系统事实，产出后确定性覆盖，不信 LLM 自报。
"""

from __future__ import annotations

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.primitives.ids import mint_chapter
from story_engine.schemas.artifacts.chapter_plan import ChapterPlan, PlanDerivedFrom
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.plan import L0, L1, L2, ChapterBeat

_ROLE = "你是长篇小说的分章规划师，负责把卷大纲落成单章的可执行方向。"
_TASK = """为本章产出 ChapterPlan。

硬要求（json 输出）：
- 本章方向必须承接「本章事件槽」：把 event 落成 chapter_goal 与 story_beats，
  接住 inherits，并在章末留下与 leaves_open 一致的未闭合压力。
- 只做**章级**决策：本章目标、推进哪条主线到什么程度、埋/收哪些伏笔、谁出场、章内粗桥段。
  **不要拆场景**，不要写台词。
- story_beats 是章内粗桥段（3~6 条），给 Director 拆场用的骨架。
- cast 只列剧情相关角色；龙套写进 background_hint，交 Director 现场引入。
- foreshadow_ops 优先处理"到期/逾期"清单里的伏笔，reason 如实填 due/overdue/organic。
- 引用已有 id（th./fs./char.）时必须原样照抄，不要另造。
- constraints 写本章硬约束（如"不得提前揭穿 fs.xxx"）。"""


def _beat_for_chapter(l2: L2 | None, chapter: int) -> ChapterBeat | None:
    if l2 is None or not l2.chapter_beats:
        return None
    for b in l2.chapter_beats:
        if b.planned_seq == chapter:
            return b
    if 1 <= chapter <= len(l2.chapter_beats):
        return l2.chapter_beats[chapter - 1]
    return None


class Planner:
    name = "planner"

    def plan(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        l0: L0,
        l1: L1,
        l2: L2 | None = None,
        arcs: list[ArcRecord] | None = None,
        due_foreshadows: list[str] | None = None,
        recent_summaries: list[str] | None = None,
        retrieved: list[str] | None = None,
        violations: str | None = None,
    ) -> ChapterPlan:
        if ctx.llm is None:
            raise ValueError("Planner 需要 LLMClient")
        beat = _beat_for_chapter(l2, chapter)
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("立意 L0（不可违背）", as_json(l0)),
                ("全书结构 L1", as_json(l1, limit=3000)),
                (
                    "本卷脊骨 volume_spine",
                    as_json(l2.volume_spine) if l2 and l2.volume_spine else "（暂无）",
                ),
                (
                    "本章事件槽（L2 chapter_beat，须承接）",
                    as_json(beat) if beat else "（暂无对应槽，按 L1/卷目标推本章）",
                ),
                ("本卷大纲 L2（全文，供对照）", as_json(l2) if l2 else "（暂无）"),
                ("台账实际进度（伏笔/主线当前状态）", as_json(arcs or [], limit=2000)),
                ("到期/逾期待收伏笔", as_json(due_foreshadows or [])),
                ("最近章摘要（防重复、接上文）", as_json(recent_summaries or [])),
                ("既有事实与线索（as-of 检索，粗画像）", as_json(retrieved or [], limit=2000)),
                ("上一轮本章被闸门拦下的违规（重规划必须避开）", violations or ""),
                ("本章章号", f"第 {chapter} 章"),
            ],
        )
        plan = ctx.llm.complete_structured(prompt, ChapterPlan, node=self.name, chapter=chapter)
        return self._anchor(plan, chapter=chapter, l1=l1, l2=l2, beat=beat)

    def _anchor(
        self,
        plan: ChapterPlan,
        *,
        chapter: int,
        l1: L1,
        l2: L2 | None,
        beat: ChapterBeat | None,
    ) -> ChapterPlan:
        """章号与追溯链由系统写死——它们是事实，不是创作。"""
        plan.chapter = mint_chapter(chapter)
        vol_id = (l2.vol_id if l2 else None) or (l1.volumes[0].vol_id if l1.volumes else "v1")
        plan.derived_from = PlanDerivedFrom(
            l2_vol_id=vol_id,
            planned_seq=beat.planned_seq if beat else chapter,
            l1_thread_ids=[t.thread_id for t in l1.threads],
            l1_fs_ids=[f.fs_id for f in l1.foreshadow_map],
        )
        return plan
