"""Faithfulness Check（守 U）—— 对应 docs/nodes/validation/faithfulness-check.md。

两道关，缺一不可：
  1. **系统**：evidence 跨度必须在 ScriptStore 里真实存在（可解析），不存在直接拒；
  2. **LLM**：跨度原文是否**蕴含**该条候选，不蕴含即幻觉，拒。

只有两关都过的候选才交 Reconciler。拒掉的记入报告，供 D 组指标统计。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import Field

from story_engine.nodes.base import NodeContext
from story_engine.nodes.prompting import as_json, build_prompt
from story_engine.nodes.validation.hard_check import resolve_span
from story_engine.schemas.artifacts.recorder_output import RecorderOutput
from story_engine.schemas.base import SchemaModel

_ROLE = "你是校验员，判断每条抽取出来的条目**是否真的被它引用的原文支持**。"
_TASK = """逐条判断：这条记录，能不能只凭它引用的那几拍原文推出来？

- 能直接推出 → entailed=true。
- 原文没说、或需要额外脑补才成立 → entailed=false，reason 写清差在哪。
- 判断标准从严：宁可拒掉一条真的，也不放进一条编的。

按给定的 index 逐条给结论，不要漏项。"""


class EntailmentVerdict(SchemaModel):
    index: int
    entailed: bool
    reason: str | None = None


class EntailmentReport(SchemaModel):
    verdicts: list[EntailmentVerdict] = Field(default_factory=list)


@dataclass
class FaithfulnessResult:
    passed: RecorderOutput
    rejected: list[dict] = field(default_factory=list)   # {kind, index, stage, reason}

    @property
    def reject_count(self) -> int:
        return len(self.rejected)


class FaithfulnessCheck:
    name = "faithfulness_check"

    def verify(
        self,
        ctx: NodeContext,
        *,
        chapter: int,
        candidates: RecorderOutput,
        script_store,
    ) -> FaithfulnessResult:
        rejected: list[dict] = []

        # ── 关 1：系统硬检（跨度存在性）──────────────────────────
        mem_ops, arc_ops, world_ops = [], [], []
        for kind, ops, keep in (
            ("mem", candidates.mem_ops, mem_ops),
            ("arc", candidates.arc_ops, arc_ops),
            ("world", candidates.world_ops, world_ops),
        ):
            for i, op in enumerate(ops):
                if not op.evidence:
                    rejected.append({"kind": kind, "index": i, "stage": "span", "reason": "evidence 为空"})
                    continue
                bad = [e.to_str() for e in op.evidence if not resolve_span(e, script_store)]
                if bad:
                    rejected.append(
                        {"kind": kind, "index": i, "stage": "span", "reason": f"跨度不存在: {bad}"}
                    )
                    continue
                keep.append(op)

        # ── 关 2：LLM 蕴含判定（只判 mem，arc/world 结构性强，M2 先信硬检）──
        if mem_ops and ctx.llm is not None:
            kept = self._entailment(ctx, chapter, mem_ops, script_store, rejected)
            mem_ops = kept

        passed = RecorderOutput(
            chapter=candidates.chapter,
            mem_ops=mem_ops,
            arc_ops=arc_ops,
            world_ops=world_ops,
            tier_noms=list(candidates.tier_noms),
            extractor_version=candidates.extractor_version,
        )
        return FaithfulnessResult(passed=passed, rejected=rejected)

    def _entailment(self, ctx: NodeContext, chapter: int, ops, script_store, rejected: list[dict]):
        items = [
            {
                "index": i,
                "text": op.text,
                "type": op.type,
                "scope": op.scope,
                "evidence": [e.to_str() for e in op.evidence],
                "原文": _quote(op.evidence, script_store),
            }
            for i, op in enumerate(ops)
        ]
        report = ctx.llm.complete_structured(
            build_prompt(_ROLE, _TASK, [("待判条目（含其引用的原文）", as_json(items, limit=6000))]),
            EntailmentReport,
            node=self.name,
            chapter=chapter,
            temperature=0,
        )
        verdict_by_index = {v.index: v for v in report.verdicts}
        kept = []
        for i, op in enumerate(ops):
            v = verdict_by_index.get(i)
            # 漏判也算没过：守 U 从严，未经确认的不进库。误杀会显式留在
            # rejected 里可观测，比静默放进一条幻觉安全。
            if v is None:
                rejected.append(
                    {"kind": "mem", "index": i, "stage": "entailment", "reason": "裁判漏判，未确认"}
                )
                continue
            if not v.entailed:
                rejected.append(
                    {"kind": "mem", "index": i, "stage": "entailment", "reason": v.reason or "不蕴含"}
                )
                continue
            kept.append(op)
        return kept


def _quote(spans, script_store) -> list[str]:
    """把 evidence 跨度还原成原文片段，喂给蕴含判定。"""
    out: list[str] = []
    for span in spans:
        script = script_store.get(f"c{span.chapter}")
        if script is None:
            continue
        for si, scene in enumerate(script.scenes, start=1):
            if span.scene is not None and si != span.scene:
                continue
            for bi, beat in enumerate(scene.beats, start=1):
                if span.beats is not None and not (span.beats[0] <= bi <= span.beats[1]):
                    continue
                out.append(f"{beat.owner}: {beat.as_text()}")
    return out
