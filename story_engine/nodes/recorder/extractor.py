"""Extractor —— 对应 docs/nodes/recorder/extractor.md。

从过闸 ChapterScript 尽力抽记忆/伏笔/世界候选（**召回优先**，精度交下游）。
每条候选必带 evidence 回指 Script 位置——跨度不存在会被 Faithfulness 硬拒。
产出是 RecorderOutput 的**候选态**：action 只是初判，最终由 Reconciler 定。
"""

from __future__ import annotations

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.schemas.artifacts.recorder_output import RecorderOutput
from story_engine.schemas.stores.script import ChapterScript

EXTRACTOR_VERSION = "m2.1"

_ROLE = "你是记录员，把本章剧本里**新发生的事实**抽成结构化条目。这是转写不是创作。"
_TASK = """通读本章剧本，抽出该记进档案的东西。

抽什么：
- mem_ops：人物的 fact（发生了什么）/ belief（他相信什么）/ trait（性格）/
  voice（口癖语气，example 填真实台词）/ ability（能力境界）/ goal（目标）。
- arc_ops：伏笔与主线的推进——埋下(PLANT)、加强(REINFORCE)、收束(FULFILL)、
  主线推进(ADVANCE)；秘密被谁知道了用 REVEAL + reveal_to。
- world_ops：本章现场造出来的新设定（地点/势力/物件…）用 REGISTER 登记；
  已有设定发生变化（据点易主等）用 UPDATE_STATE。

硬要求：
- **每条都必须有 evidence**，格式 {"chapter": n, "scene": m, "beats": [起, 止]}，
  指向真实存在的拍。宁可不抽，不可乱指。
- 宁滥勿缺（召回优先），但**只抽剧本里真写了的**，不要推断、不要脑补后续。
- scope 用 char.{slug} / th.{slug} / global；引用已有 id 时原样照抄。
- arc_ops.target_id 优先用台账已有的 fs./th./sec.；若是本章新冒出的伏笔/主线，
  必须 is_new=true 并给 draft.desc，id 形如 fs.{slug}。
- mem_ops 的 action 一律先填 ADD（是否改成加强/失效由下游对账决定）。
- 秘密不要进 mem_ops，走 arc_ops。"""


class Extractor:
    name = "extractor"

    def extract(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        script: ChapterScript,
        related_memories: list[dict] | None = None,
    ) -> RecorderOutput:
        if ctx.llm is None:
            raise ValueError("Extractor 需要 LLMClient")
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("本章剧本（过闸主真相）", _render(script)),
                ("相关旧记忆（供判断哪些是新的）", as_json(related_memories or [], limit=2000)),
                ("本章章号", f"第 {chapter} 章（evidence 的 chapter 一律填 {chapter}）"),
            ],
        )
        out = ctx.llm.complete_structured(
            prompt, RecorderOutput, node=self.name, chapter=chapter, temperature=0
        )
        out.chapter = chapter
        out.extractor_version = EXTRACTOR_VERSION
        return out


def _render(script: ChapterScript) -> str:
    """带位置标注的剧本全文——标注是为了让 LLM 能填出正确的 evidence。"""
    lines: list[str] = []
    for si, scene in enumerate(script.scenes, start=1):
        lines.append(f"[场 {si}] 地点={scene.location} POV={scene.pov} 目标={scene.goal}")
        for bi, beat in enumerate(scene.beats, start=1):
            lines.append(f"  (s{si}.b{bi}) {beat.owner}: {beat.as_text()}")
    return "\n".join(lines)
