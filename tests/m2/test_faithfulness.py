"""Faithfulness Check（守 U）UT：跨度硬检 + 蕴含判定的从严纪律。

裁判漏判 = 未确认 = 不进库。误杀显式留在 rejected 里可观测，
好过静默放进一条幻觉。
"""

import json

from story_engine.llm.base import Completion, LLMClient
from story_engine.nodes.base import NodeContext
from story_engine.nodes.validation.faithfulness_check import FaithfulnessCheck
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.artifacts.recorder_output import MemOp, RecorderOutput
from story_engine.schemas.stores.script import Beat, ChapterScript, Scene
from story_engine.stores.json_backend import JsonStore


class _Judge:
    """按给定 verdicts 作答的假裁判。"""

    model = "judge"

    def __init__(self, verdicts: list[dict]) -> None:
        self.payload = json.dumps({"verdicts": verdicts}, ensure_ascii=False)

    def complete(self, prompt: str, **cfg: object) -> Completion:
        return Completion(text=self.payload, prompt_tokens=1, completion_tokens=1, model=self.model)


def _store(tmp_path) -> JsonStore[ChapterScript]:
    store: JsonStore[ChapterScript] = JsonStore(
        ChapterScript, tmp_path / "script.jsonl", key_field="chapter"
    )
    store.append(
        ChapterScript(
            chapter="c1", volume="v1", theme="入门", tone="热血",
            scenes=[
                Scene(
                    scene_id="c1.s1", location="loc.qing_yun", pov="char.ye_fan",
                    goal="叩门", conflict="门规", contract_ref="c1.s1",
                    beats=[
                        Beat(beat_id="c1.s1.b1", owner="char.ye_fan",
                             dramatic_goal="表明来意", type="dialogue",
                             dialogue={"line": "我要拜入青云门。"}),
                    ],
                )
            ],
        )
    )
    return store


def _op(text: str, span: str) -> MemOp:
    return MemOp(
        action="ADD", type="fact", scope="char.ye_fan", text=text,
        evidence=[EvidenceSpan.parse(span)],
    )


def _candidates(*ops: MemOp) -> RecorderOutput:
    return RecorderOutput(chapter=1, mem_ops=list(ops))


def test_missing_verdict_is_rejected(tmp_path):
    """裁判只对 index 0 作答，漏了 index 1 → 漏的那条按未确认拒掉。"""
    ctx = NodeContext(llm=LLMClient(_Judge([{"index": 0, "entailed": True}])))
    candidates = _candidates(
        _op("叶凡要拜入青云门", "c1.s1.b1"),
        _op("叶凡其实是荒古后裔", "c1.s1.b1"),
    )

    res = FaithfulnessCheck().verify(
        ctx, chapter=1, candidates=candidates, script_store=_store(tmp_path)
    )

    assert [op.text for op in res.passed.mem_ops] == ["叶凡要拜入青云门"]
    missed = [r for r in res.rejected if r["stage"] == "entailment"]
    assert len(missed) == 1
    assert missed[0]["index"] == 1 and "漏判" in missed[0]["reason"]


def test_not_entailed_is_rejected_with_reason(tmp_path):
    ctx = NodeContext(
        llm=LLMClient(_Judge([{"index": 0, "entailed": False, "reason": "原文没提身世"}]))
    )
    res = FaithfulnessCheck().verify(
        ctx, chapter=1,
        candidates=_candidates(_op("叶凡其实是荒古后裔", "c1.s1.b1")),
        script_store=_store(tmp_path),
    )
    assert res.passed.mem_ops == []
    assert res.rejected[0]["reason"] == "原文没提身世"


def test_dangling_span_rejected_before_judge(tmp_path):
    """跨度指向不存在的拍：系统硬检直接拒，不必惊动裁判。"""
    ctx = NodeContext(llm=LLMClient(_Judge([])))
    res = FaithfulnessCheck().verify(
        ctx, chapter=1,
        candidates=_candidates(_op("凭空捏造", "c1.s9.b9")),
        script_store=_store(tmp_path),
    )
    assert res.passed.mem_ops == []
    assert res.rejected[0]["stage"] == "span"
