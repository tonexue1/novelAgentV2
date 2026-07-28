"""Summarizer —— 对应 docs/nodes/recorder/summarizer.md。

章末产 scene / chapter 多分辨率摘要（蒸馏梗概 + 轻结构化 facet）。
写入走独立 SummaryDelta，不并入 RecorderOutput。(level,ref) 幂等由 Applier 保证。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.script import ChapterScript
from story_engine.schemas.stores.summary import SummaryDelta, SummaryEntry

SUMMARIZER_VERSION = "m4a.1"

_ROLE = "你是摘要员，把本章剧本蒸馏成多分辨率梗概。这是压缩不是创作。"
_TASK = """为本章产出摘要条目：
1) 每个场一条 level=scene，ref=场 id（如 c1.s1）
2) 整章一条 level=chapter，ref=章 id（如 c1）

硬要求：
- text 是蒸馏梗概（2~4 句），只写剧本里发生过的，不推断。
- covers 回指源位置：scene 级填该场 beats 跨度；chapter 级可只填整章。
- cast / threads 填本章涉及的角色与主线 id（有则填，无则空数组）。
- 不要编造 id。"""


class _SummarizerLLMOut(SchemaModel):
    entries: list[SummaryEntry] = Field(default_factory=list)


class Summarizer:
    name = "summarizer"

    def summarize(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        script: ChapterScript,
    ) -> SummaryDelta:
        if ctx.llm is None:
            raise ValueError("Summarizer 需要 LLMClient")
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("本章剧本", _render(script)),
                ("章号 / 章 id", f"第 {chapter} 章；chapter ref={script.chapter}"),
            ],
        )
        out = ctx.llm.complete_structured(
            prompt, _SummarizerLLMOut, node=self.name, chapter=chapter, temperature=0
        )
        entries = _normalize(out.entries, script, chapter)
        return SummaryDelta(
            chapter=chapter,
            entries=entries,
            produced_by="Summarizer",
        )


def _normalize(entries: list[SummaryEntry], script: ChapterScript, chapter: int) -> list[SummaryEntry]:
    """系统侧补齐版本号与缺省 covers；过滤非法 level。"""
    scene_ids = {s.scene_id for s in script.scenes}
    out: list[SummaryEntry] = []
    for e in entries:
        if e.level not in ("scene", "chapter"):
            continue
        if e.level == "scene" and e.ref not in scene_ids:
            continue
        if e.level == "chapter" and e.ref != script.chapter:
            e = e.model_copy(update={"ref": script.chapter})
        if not e.covers:
            if e.level == "chapter":
                e = e.model_copy(update={"covers": [EvidenceSpan(chapter=chapter)]})
            else:
                # c{n}.s{m}
                try:
                    scene_no = int(e.ref.rsplit(".s", 1)[-1])
                    e = e.model_copy(
                        update={"covers": [EvidenceSpan(chapter=chapter, scene=scene_no)]}
                    )
                except ValueError:
                    pass
        e = e.model_copy(update={
            "t_valid": chapter,
            "produced_by": "Summarizer",
            "summarizer_version": SUMMARIZER_VERSION,
        })
        out.append(e)
    # 若 LLM 漏了 chapter 级，确定性补一条极简
    if not any(e.level == "chapter" for e in out):
        texts = [b.as_text() for s in script.scenes for b in s.beats]
        out.append(SummaryEntry(
            level="chapter",
            ref=script.chapter,
            text=" / ".join(texts[:6])[:400] or f"{script.chapter} 摘要",
            covers=[EvidenceSpan(chapter=chapter)],
            t_valid=chapter,
            produced_by="Summarizer",
            summarizer_version=SUMMARIZER_VERSION,
        ))
    return out


def _render(script: ChapterScript) -> str:
    lines: list[str] = [f"章 {script.chapter}"]
    for si, scene in enumerate(script.scenes, start=1):
        lines.append(f"[场 {si} id={scene.scene_id}] 地点={scene.location} POV={scene.pov}")
        for bi, beat in enumerate(scene.beats, start=1):
            lines.append(f"  (b{bi}) {beat.owner}: {beat.as_text()}")
    return "\n".join(lines)
