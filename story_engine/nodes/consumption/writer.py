"""Writer（写作器）—— 对应 docs/nodes/consumption/writer.md。

消费层：读剧本渲染成散文。**只读 Script**，不回写真相层；可重复渲染。
这是全系统唯一产自由文本的地方（成品层）。
"""

from __future__ import annotations

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.schemas.stores.manuscript import Manuscript
from story_engine.schemas.stores.script import ChapterScript

_ROLE = "你是小说家，把一份剧本渲染成正式的小说章节。"
_TASK = """把剧本写成散文。

- 剧本里的台词、动作、心理**都要落进正文**，但由你决定怎么呈现：
  加旁白描写、环境烘托、节奏停顿。
- **不得增删剧情事实**：没写的事不要发明，写了的事不要漏。
- 心理活动用叙述转写，别标"（内心）"这种舞台提示。
- 不要输出场次标题、编号、元信息，直接给正文。
- 用中文，保持前文一致的文风。"""


class Writer:
    name = "writer"

    def render(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        script: ChapterScript,
        style: str | None = None,
        previous_tail: str | None = None,
    ) -> Manuscript:
        if ctx.llm is None:
            raise ValueError("Writer 需要 LLMClient")
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("本章剧本", _render_script(script)),
                ("章节基调", as_json({"theme": script.theme, "tone": script.tone})),
                ("文风要求", style or "第三人称限知，白描为主，克制抒情"),
                ("上一章结尾（接住语气，不要重复内容）", (previous_tail or "")[-800:]),
            ],
        )
        text = ctx.llm.complete_text(prompt, node=self.name, chapter=chapter)
        return Manuscript(
            chapter=script.chapter,
            text=text,
            style=style,
            rendered_from=script.chapter,
        )


def _render_script(script: ChapterScript) -> str:
    lines: list[str] = []
    for scene in script.scenes:
        lines.append(
            f"【场景 {scene.scene_id}】地点={scene.location} POV={scene.pov} "
            f"氛围={scene.mood or '—'} 目标={scene.goal} 冲突={scene.conflict}"
        )
        for beat in scene.beats:
            if beat.type == "dialogue" and beat.dialogue:
                sub = f"（潜台词：{beat.dialogue.subtext}）" if beat.dialogue.subtext else ""
                tone = f"[{beat.dialogue.tone}]" if beat.dialogue.tone else ""
                lines.append(f"  {beat.owner}{tone}：「{beat.dialogue.line}」{sub}")
            elif beat.type == "action" and beat.action:
                lines.append(f"  [动作] {beat.action.stage}")
            elif beat.type == "thought" and beat.thought:
                lines.append(f"  [{beat.owner} 心理] {beat.thought.inner}")
    return "\n".join(lines)
