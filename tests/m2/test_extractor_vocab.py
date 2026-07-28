"""schema.llm_vocab 与 Extractor prompt 挂载。"""

from story_engine.llm.base import Completion, LLMClient
from story_engine.nodes.base import NodeContext
from story_engine.nodes.recorder.extractor import Extractor
from story_engine.primitives.enums import Importance
from story_engine.schemas.artifacts.recorder_output import (
    ArcOp,
    MemOp,
    RecorderOutput,
    WorldOp,
)
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.plan import PayoffDeadline
from tests.factories import make_beat, make_chapter_script, make_scene


def test_recorder_output_vocab_covers_world_and_arc_rules():
    text = RecorderOutput.llm_vocab()
    assert "concept | art | location | faction | item | race" in text
    assert "禁止" in text and "character" in text
    assert "PLANNED" in text and "REINFORCE" in text
    assert "MemOp" in text and WorldOp.llm_vocab() in text
    assert ArcOp.llm_vocab() in text
    assert MemOp.llm_vocab() in text


def test_arc_input_brief_lists_state():
    arcs = [
        ArcRecord(
            id="fs.jade",
            kind="foreshadow",
            desc="玉",
            state="PLANNED",
            importance=Importance.CORE,
            payoff_deadline=PayoffDeadline(granularity="chapter", ref="c10"),
        )
    ]
    brief = ArcRecord.llm_input_brief(arcs)
    assert "fs.jade" in brief
    assert "PLANNED" in brief
    assert "不能 REINFORCE" in brief or "只能 PLANT" in brief


class _Capture:
    model = "cap"
    last_prompt: str = ""

    def complete(self, prompt: str, **cfg: object) -> Completion:
        type(self).last_prompt = prompt
        # 最小合法 RecorderOutput
        return Completion(
            text='{"chapter":1,"mem_ops":[],"arc_ops":[],"world_ops":[],"tier_noms":[]}',
            prompt_tokens=1,
            completion_tokens=1,
            model=self.model,
        )


def test_extractor_prompt_includes_schema_vocab_and_arc_input():
    _Capture.last_prompt = ""
    ctx = NodeContext(llm=LLMClient(_Capture()))
    script = make_chapter_script(
        chapter="c1",
        scenes=[make_scene(beats=[make_beat(owner="char.a", text="你好")])],
    )
    arcs = [
        ArcRecord(
            id="fs.x", kind="foreshadow", desc="x", state="PLANNED",
            importance=Importance.MINOR,
        )
    ]
    out = Extractor().extract(
        ctx, chapter=1, script=script, related_memories=[], arcs=arcs,
    )
    prompt = _Capture.last_prompt
    assert "输出契约" in prompt
    assert "WorldOp" in prompt
    assert "fs.x" in prompt
    assert "PLANNED" in prompt
    assert out.extractor_version.startswith("m2.")
    assert out.chapter == 1
