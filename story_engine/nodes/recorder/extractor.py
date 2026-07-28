"""Extractor —— 对应 docs/nodes/recorder/extractor.md。

从过闸 ChapterScript 尽力抽记忆/伏笔/世界候选（**召回优先**，精度交下游）。
每条候选必带 evidence 回指 Script 位置——跨度不存在会被 Faithfulness 硬拒。
产出是 RecorderOutput 的**候选态**：action 只是初判，最终由 Reconciler 定。

取值说明由 schema.llm_vocab / llm_input_brief 自带，禁止在本文件手抄枚举第三份。
"""

from __future__ import annotations

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.schemas.artifacts.recorder_output import RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.schemas.stores.script import ChapterScript

EXTRACTOR_VERSION = "m2.2"

_ROLE = "你是记录员，把本章剧本里**新发生的事实**抽成结构化条目。这是转写不是创作。"
_TASK = """通读本章剧本，抽出该记进档案的东西。

分拣（详见「输出契约」分节，取值以契约为准）：
- 人物事实/信念/性格/能力/目标 → mem_ops（scope=char.*）
- 伏笔/秘密/主线推进 → arc_ops（必须对照「伏笔/主线台账」的当前 state）
- 地点/势力/功法/物件/种族等设定 → world_ops（禁止角色）
- 人物分级提名极少用 → tier_noms

硬要求：
- **每条都必须有 evidence**，指向真实存在的拍；宁可不抽，不可乱指。
- 宁滥勿缺（召回优先），但**只抽剧本里真写了的**，不要推断、不要脑补后续。
- mem_ops 的 action 一律先填 ADD。
- 秘密不要进 mem_ops，走 arc_ops。
- 输出 JSON 必须符合「输出契约」中的合法取值；冲突时以契约为准。"""


class Extractor:
    name = "extractor"

    def extract(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        script: ChapterScript,
        related_memories: list[dict] | None = None,
        arcs: list[ArcRecord] | None = None,
    ) -> RecorderOutput:
        if ctx.llm is None:
            raise ValueError("Extractor 需要 LLMClient")
        arcs = arcs or []
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("输出契约（schema 自带取值）", RecorderOutput.llm_vocab()),
                ("入参：伏笔/主线台账", ArcRecord.llm_input_brief(arcs)),
                (
                    "入参：相关旧记忆",
                    MemoryEntry.llm_vocab()
                    + "\n"
                    + as_json(related_memories or [], limit=2000),
                ),
                ("入参：本章剧本（过闸主真相）", _render(script)),
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
