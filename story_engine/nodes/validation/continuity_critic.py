"""Continuity Critic（续写评审，守 f 的软判层）—— 对应 docs/nodes/validation/continuity-critic.md。

每场 Script 收束后一道，管硬检判不了的：OOC、穿帮（推翻既有 canon）、逻辑、语气。
**独立做一次针对性宽检索**（"这场戏可能推翻哪些既有设定？"），兜底生成器因预算漏掉的伏笔。

只产 `Violation[]`，PASS 就是空列表——严重度已在 severity 里，不另造 verdict 枚举。
beat 级 OOC 由逐拍硬检当场抓（只重调该拍），这里看的是整场。
"""

from __future__ import annotations

from pydantic import Field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.primitives.enums import Severity
from story_engine.primitives.ids import mint_violation_id
from story_engine.schemas.base import SchemaModel
from story_engine.schemas.stores.violation import Locus, Violation

_ROLE = "你是续写评审，负责挑出这一场戏里「不该发生」的东西。"
_TASK = """对照既有设定审这一场，只挑**实打实的问题**，挑不出就交空列表。

看四类：
- OOC：说话做事违背这个人的性格/三观/语气样本。
- canon_contradiction：推翻了既有事实、设定或时间线（含"他怎么会知道"——引用了自己不知情的秘密）。
- logic：场内因果说不通、承重拍没落地、动机断裂、少一拍铺垫。
- voice：语气/文风跑偏。

硬要求：
- 每条问题指到具体的 beat_id（拿不准就留空，指到场）。
- message 写"哪里错、和什么冲突"；suggestion 写一句可执行的改法。
- refs 填被违背的既有条目 id（m./fs./th./sec./loc. 等）；标 BLOCK 时 **必须非空**。
- severity（焊死，违反会被系统降级）：
  - **禁止**对 logic / voice / OOC 标 BLOCK——这些最多 CORRECT。
  - BLOCK **仅限** canon_contradiction，且能指出被推翻的既有条目：时间线矛盾 /
    死人说话 / 认知边界穿帮 / 推翻已入库事实。空口指控（refs 空）不算。
  - OOC、局部逻辑、动机不足、语气偏 → CORRECT；轻微风格瑕疵 → ADVISORY。
- **不要**为了交差硬凑问题；没问题就 findings 空着。
- 系统会把违规的 BLOCK（logic/voice/OOC/无 refs）强制降为 CORRECT——别指望用 BLOCK 换场重导。"""

_ALLOWED_CATEGORIES = {"OOC", "canon_contradiction", "voice", "logic"}
_SOFT_CATEGORIES = frozenset({"logic", "voice", "OOC", "other"})
_SEVERITY_BY_NAME = {s.value: s for s in Severity}


class CriticFinding(SchemaModel):
    severity: str = "CORRECT"
    category: str = "logic"
    beat_id: str | None = None
    message: str
    suggestion: str | None = None
    refs: list[str] = Field(default_factory=list)


class CriticReport(SchemaModel):
    findings: list[CriticFinding] = Field(default_factory=list)


class ContinuityCritic:
    name = "continuity_critic"

    def review(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        scene,
        contract=None,
        context=None,          # AssembledContext（Critic 宽画像）
        recent_summaries: list[str] | None = None,
    ) -> list[Violation]:
        """返回 Violation[]；空列表 = 过。没接 LLM 时静默放行（硬检仍在）。"""
        if ctx.llm is None:
            return []
        prompt = build_prompt(
            _ROLE,
            _TASK,
            [
                ("这一场（待审）", as_json(_scene_view(scene), limit=6000)),
                ("本场合同（承重拍与退出条件）", as_json(contract, limit=2000) if contract else ""),
                (
                    "既有设定与事实（独立宽检索，as-of）",
                    as_json(context.facts() if context else [], limit=4000),
                ),
                (
                    "各角色认知边界（as-of 知情的秘密）",
                    as_json(context.cognition if context else {}),
                ),
                ("前一状态（最近章摘要）", as_json(recent_summaries or [])),
                ("当前章号", f"第 {chapter} 章"),
            ],
        )
        report = ctx.llm.complete_structured(
            prompt, CriticReport, node=self.name, chapter=chapter, temperature=0
        )
        return [self._to_violation(f, chapter=chapter, scene=scene) for f in report.findings]

    def _to_violation(self, f: CriticFinding, *, chapter: int, scene) -> Violation:
        beat_ids = {b.beat_id for b in scene.beats}
        beat = f.beat_id if f.beat_id in beat_ids else None
        category = f.category if f.category in _ALLOWED_CATEGORIES else "other"
        refs = list(f.refs)
        return Violation(
            id=mint_violation_id(),
            chapter=chapter,
            stage="character",  # 评的是 Character 产物
            check_type="llm",
            severity=_clamp_severity(_norm_severity(f.severity), category, refs),
            category=category,
            locus=Locus(chapter=f"c{chapter}", scene=scene.scene_id, beat=beat),
            refs=refs,
            message=f.message,
            suggestion=f.suggestion,
            escalation_level="scene",
        )


def _norm_severity(name: str) -> Severity:
    """认不出的档位按最轻处理——评审瞎报一个词不该把整章挂起。"""
    return _SEVERITY_BY_NAME.get((name or "").strip().upper(), Severity.ADVISORY)


def _clamp_severity(severity: Severity, category: str, refs: list[str]) -> Severity:
    """模型常把「少铺垫」标成 BLOCK/logic；代码焊死，不靠自觉。

    BLOCK 仅保留：canon_contradiction 且 refs 非空。其余 BLOCK → CORRECT。
    """
    if severity != Severity.BLOCK:
        return severity
    if category in _SOFT_CATEGORIES:
        return Severity.CORRECT
    if category == "canon_contradiction" and not refs:
        return Severity.CORRECT
    return severity


def _scene_view(scene) -> dict:
    """整场的紧凑视图：审的是内容，不是 schema。"""
    return {
        "scene_id": scene.scene_id,
        "location": scene.location,
        "pov": scene.pov,
        "goal": scene.goal,
        "conflict": scene.conflict,
        "cast": [{"char": c.char, "entry_state": c.entry_state} for c in scene.cast],
        "beats": [
            {
                "beat_id": b.beat_id,
                "owner": b.owner,
                "type": b.type,
                "dramatic_goal": b.dramatic_goal,
                "hits": b.hits,
                "text": b.as_text(),
                "subtext": b.dialogue.subtext if b.dialogue else None,
            }
            for b in scene.beats
        ],
    }
