"""Reconciler 守卫 UT：软失效不删 / REINFORCE 必带真 target_id / NOOP 留档 / 去重。

LLM 判语义，系统兜底——这里测的是兜底那半边，所以假 LLM 直接返回"坏"决策。
"""

import json

import pytest

from story_engine.llm.base import Completion, LLMClient
from story_engine.nodes.base import NodeContext
from story_engine.nodes.recorder.reconciler import Reconciler
from story_engine.nodes.system.applier import Applier
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.schemas.artifacts.recorder_output import ArcOp, MemOp, RecorderOutput
from story_engine.schemas.stores.arc import ArcRecord
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.stores.json_backend import JsonStore


class _Canned:
    """固定吐一份 ReconcilerOutput 的假 provider。"""

    model = "canned"

    def __init__(self, mem_ops: list[dict]) -> None:
        self.payload = json.dumps({"mem_ops": mem_ops}, ensure_ascii=False)

    def complete(self, prompt: str, **cfg: object) -> Completion:
        return Completion(text=self.payload, prompt_tokens=1, completion_tokens=1, model=self.model)


def _ctx(mem_ops: list[dict]) -> NodeContext:
    return NodeContext(llm=LLMClient(_Canned(mem_ops)))


def _old(text: str = "叶凡拜入青云门") -> MemoryEntry:
    return MemoryEntry(
        id="m.old", type="fact", scope="char.ye_fan", text=text, t_valid=1,
        evidence=[EvidenceSpan.parse("c1.s1.b1")],
    )


def _candidates() -> RecorderOutput:
    return RecorderOutput(
        chapter=2,
        mem_ops=[MemOp(action="ADD", type="fact", scope="char.ye_fan", text="又一次印证",
                       evidence=[EvidenceSpan.parse("c2.s1.b1")])],
    )


def test_reinforce_without_target_downgrades_to_add():
    """LLM 判 REINFORCE 却没给 target_id：有载荷就降级成 ADD，不能丢数据。"""
    ctx = _ctx([{
        "action": "REINFORCE", "type": "fact", "scope": "char.ye_fan",
        "text": "他确实入了门", "evidence": [{"chapter": 2, "scene": 1, "beats": [1, 1]}],
    }])
    res = Reconciler().reconcile(ctx, chapter=2, candidates=_candidates(), related=[_old()])
    assert [op.action for op in res.output.mem_ops] == ["ADD"]
    assert res.coerced[0]["from"] == "REINFORCE" and res.coerced[0]["to"] == "ADD"


def test_reinforce_with_unknown_target_downgrades_to_noop():
    """指向库里没有的 id 且无载荷：只能 NOOP——绝不放给 fail-fast 的 Applier。"""
    ctx = _ctx([{"action": "REINFORCE", "target_id": "m.ghost"}])
    res = Reconciler().reconcile(ctx, chapter=2, candidates=_candidates(), related=[_old()])
    assert [op.action for op in res.output.mem_ops] == ["NOOP"]
    assert "不存在" in res.coerced[0]["reason"]


def test_duplicate_add_becomes_noop():
    """措辞不同但语义同一条（去重键 = scope+type+归一化 text）→ 不再 ADD 第二条。"""
    ctx = _ctx([{
        "action": "ADD", "type": "fact", "scope": "char.ye_fan",
        "text": "叶凡，拜入青云门。", "evidence": [{"chapter": 2, "scene": 1, "beats": [1, 1]}],
    }])
    res = Reconciler().reconcile(ctx, chapter=2, candidates=_candidates(), related=[_old()])
    assert [op.action for op in res.output.mem_ops] == ["NOOP"]
    assert res.coerced[0]["reason"] == "与旧档案重复"


def test_no_related_skips_llm():
    """第 1 章无旧档案可对：不打 LLM，候选原样放行。"""
    ctx = NodeContext(llm=None)
    res = Reconciler().reconcile(ctx, chapter=1, candidates=_candidates(), related=[])
    assert [op.action for op in res.output.mem_ops] == ["ADD"]


def test_soft_invalidate_does_not_delete(tmp_path):
    """矛盾走软失效：条目仍在库里，只是 as-of 之后不可见。"""
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    mem.append(MemoryEntry(id="m.goal", type="goal", scope="char.ye_fan", text="拜入宗门", t_valid=1))

    ctx = _ctx([{"action": "SOFT-INVALIDATE", "target_id": "m.goal", "resolution": "achieved"}])
    res = Reconciler().reconcile(
        ctx, chapter=2, candidates=_candidates(), related=[mem.get("m.goal")]
    )
    Applier().apply_recorder_output(res.output, mem, arc)

    entry = mem.get("m.goal")
    assert entry is not None                      # 没删
    assert entry.t_invalid == 2 and entry.resolution == "achieved"
    assert entry.visible_as_of(1) and not entry.visible_as_of(2)


def test_noop_is_logged_not_applied(tmp_path):
    """NOOP 留档供审计/幂等重建，Applier 只记日志不碰库。"""
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    ro = RecorderOutput(chapter=2, mem_ops=[MemOp(action="NOOP", target_id="m.old")])

    result = Applier().apply_recorder_output(ro, mem, arc)
    assert result.noops == ["m.old"]
    assert len(mem) == 0


def test_applier_rejects_dangling_reinforce(tmp_path):
    """Applier 对悬空 target 是 fail-fast 的——正是 Reconciler 必须兜住的原因。"""
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    ro = RecorderOutput(chapter=2, mem_ops=[MemOp(action="REINFORCE", target_id="m.ghost")])
    with pytest.raises(ValueError, match="REINFORCE 目标不存在"):
        Applier().apply_recorder_output(ro, mem, arc)


def test_ghost_arc_without_is_new_promoted_to_emergent(tmp_path):
    """Extractor 捏了台账没有的弧线 id 且忘了 is_new → 升为涌现，不炸 Applier。"""
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    candidates = RecorderOutput(
        chapter=3,
        arc_ops=[
            ArcOp(
                target_id="foreshadow_cross_path_ch3",
                kind="foreshadow",
                op="PLANT",
                evidence=[EvidenceSpan.parse("c3.s1.b1")],
            )
        ],
    )
    res = Reconciler().reconcile(
        ctx=NodeContext(llm=None),
        chapter=3,
        candidates=candidates,
        related=[],
        arcs=[],
    )
    assert res.output.arc_ops[0].is_new is True
    assert res.output.arc_ops[0].target_id == "fs.foreshadow_cross_path_ch3"
    assert any(c.get("to") == "is_new" for c in res.coerced)
    Applier().apply_recorder_output(res.output, mem, arc)
    assert arc.get("fs.foreshadow_cross_path_ch3") is not None


def test_thread_op_on_foreshadow_coerced_to_noop(tmp_path):
    """Extractor 对伏笔误发 ADVANCE（thread 专用）→ 降 NOOP，不炸 Applier。"""
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    arc.append(
        ArcRecord(id="fs.debt", kind="foreshadow", state="PLANTED", desc="欠债", origin="planned")
    )
    candidates = RecorderOutput(
        chapter=3,
        arc_ops=[
            ArcOp(
                target_id="fs.debt",
                kind="foreshadow",
                op="ADVANCE",
                milestone="被骗加深",
                evidence=[EvidenceSpan.parse("c3.s1.b1")],
            )
        ],
    )
    res = Reconciler().reconcile(
        ctx=NodeContext(llm=None),
        chapter=3,
        candidates=candidates,
        related=[],
        arcs=arc.all(),
    )
    assert res.output.arc_ops[0].op == "NOOP"
    assert any("不适用于 foreshadow" in c.get("reason", "") for c in res.coerced)
    Applier().apply_recorder_output(res.output, mem, arc)
    assert arc.get("fs.debt").state == "PLANTED"
