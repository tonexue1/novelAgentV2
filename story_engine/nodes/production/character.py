"""Character —— 对应 docs/nodes/production/character.md。

演一拍：拿本拍戏剧目标 + 单角色画像 + 工作缓冲（POV 过滤），产**实现段**。
派工段（owner/dramatic_goal/hits）不归它写——内容自主、流向他定。

认知边界：只喂该角色 as-of 知道的东西；不知道的绝不能从嘴里说出来。
"""

from __future__ import annotations

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.schemas.artifacts.scene_script import BeatDispatch, SceneContract
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.script import Action, Beat, Dialogue, Handoff, Thought

_ROLE = "你是一名演员，此刻只演一个角色、只演一拍。你不是叙述者，不要写旁白。"
_TASK = """按派工的戏剧目标，演出**这一拍**。

三选一（type 字段）：
- dialogue：这一拍是说话。填 dialogue.line（台词原文），subtext 写潜台词，tone 写语气。
- action：这一拍是动作/环境事件。填 action.stage（做了什么，第三人称白描）。
- thought：这一拍是心理活动。填 thought.inner。

硬要求：
- **只演一拍**，不要把整场演完，不要替别人说话。
- 严守认知边界：你不知道的事绝不能说出口、也不能在心理活动里想到。
- 台词要贴合你的语气样本；没有样本就按画像推。
- handoff 告诉调度你把球传给谁：ADDRESS（对某人说）/ DEMAND（逼某人回应）/
  EXIT（我要走了）/ NONE。target 填 char.{slug}。
- owner 为 ENV / NARRATION 时**不得**用 dialogue。"""


class BeatRealization(SchemaModel):
    """Character 只填实现段 + handoff；派工段由 dispatch 持有。"""

    type: str                                  # dialogue | action | thought
    dialogue: Dialogue | None = None
    action: Action | None = None
    thought: Thought | None = None
    handoff: Handoff | None = None


class Character:
    name = "character"

    def act(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        dispatch: BeatDispatch,
        contract: SceneContract,
        profile: dict | None = None,
        voice_examples: list[str] | None = None,
        known_facts: list[str] | None = None,
        buffer: list[Beat] | None = None,
    ) -> Beat:
        if ctx.llm is None:
            raise ValueError("Character 需要 LLMClient")
        entry = next(
            (c for c in contract.cast if c.char == dispatch.owner),
            None,
        )
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("你是谁（画像）", as_json(profile or {"char": dispatch.owner})),
                ("你的语气样本", as_json(voice_examples or [])),
                ("你此刻想要什么（场级动机）", (entry.scene_goal or "") if entry else ""),
                ("你此刻的处境", (entry.entry_state or "") if entry else ""),
                ("你知道的事（认知边界内，之外的一概不知）", as_json(known_facts or [])),
                ("本场情境", as_json(_scene_brief(contract))),
                ("本场已经发生了什么（按你的视角）", as_json(_visible(buffer or []), limit=2500)),
                ("本拍派工：你的戏剧目标", dispatch.dramatic_goal),
                ("额外调度提示", dispatch.directive or ""),
            ],
        )
        real = ctx.llm.complete_structured(
            prompt, BeatRealization, node=self.name, chapter=chapter
        )
        return self._assemble(real, dispatch)

    def _assemble(self, real: BeatRealization, dispatch: BeatDispatch) -> Beat:
        """派工段 + 实现段合成一拍。beat_id 是临时值，Applier 落库时重铸。"""
        kind = real.type if real.type in {"dialogue", "action", "thought"} else "action"
        dialogue, action, thought = real.dialogue, real.action, real.thought
        if kind == "dialogue" and dispatch.owner in {"ENV", "NARRATION"}:
            # 非角色 owner 不得有台词：降级成环境白描，比整拍重来便宜
            kind, action, dialogue = "action", Action(stage=real.dialogue.line if real.dialogue else ""), None
        payload = {"dialogue": dialogue, "action": action, "thought": thought}
        if payload[kind] is None:  # LLM 报了 type 却没填对应段，兜一个空壳免得整章崩
            payload[kind] = {
                "dialogue": Dialogue(line=""),
                "action": Action(stage=""),
                "thought": Thought(inner=""),
            }[kind]
        return Beat(
            beat_id="tmp",
            owner=dispatch.owner,
            dramatic_goal=dispatch.dramatic_goal,
            hits=dispatch.hits,
            type=kind,  # type: ignore[arg-type]
            dialogue=payload["dialogue"] if kind == "dialogue" else None,
            action=payload["action"] if kind == "action" else None,
            thought=payload["thought"] if kind == "thought" else None,
            handoff=real.handoff,
        )


def _scene_brief(contract: SceneContract) -> dict:
    return {
        "location": contract.location,
        "goal": contract.goal,
        "conflict": contract.conflict,
        "cast": [c.char for c in contract.cast],
    }


def _visible(buffer: list[Beat]) -> list[dict]:
    """工作缓冲按 POV 过滤：别人的心理活动你看不见。"""
    out: list[dict] = []
    for b in buffer:
        if b.type == "thought":
            continue
        out.append({"owner": b.owner, "text": b.as_text()})
    return out
