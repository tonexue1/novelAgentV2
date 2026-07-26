"""Assembler：节点画像、POV 认知边界、预算截断顺序。"""

import pytest

from story_engine.nodes.system.assembler import Assembler
from story_engine.schemas.stores.arc import ArcRecord, Knowledge
from story_engine.schemas.stores.memory import MemoryEntry
from story_engine.stores.json_backend import JsonStore


def _stores(tmp_path):
    mem: JsonStore[MemoryEntry] = JsonStore(MemoryEntry, tmp_path / "m.jsonl", key_field="id")
    arc: JsonStore[ArcRecord] = JsonStore(ArcRecord, tmp_path / "a.jsonl", key_field="id")
    return mem, arc


def _mem(mid: str, scope: str, text: str, salience: float, *, mtype: str = "fact", ch: int = 1):
    return MemoryEntry(id=mid, type=mtype, scope=scope, text=text, t_valid=ch, salience=salience)


def test_pov_boundary_hides_unknown_secret(tmp_path):
    mem, arc = _stores(tmp_path)
    mem.append(_mem("m.1", "char.a", "甲的往事", 0.6))
    mem.append(_mem("m.2", "char.b", "乙的往事", 0.6))
    arc.append(
        ArcRecord(id="sec.blood", kind="secret", state="PLANTED", desc="魔族血脉",
                  knowledge=[Knowledge(char="char.a", since_ch=1)])
    )
    asm = Assembler()

    a = asm.assemble(node="character", chapter=5, mem_store=mem, arc_store=arc, char="char.a")
    b = asm.assemble(node="character", chapter=5, mem_store=mem, arc_store=arc, char="char.b")

    assert "sec.blood" in a.refs()
    assert "sec.blood" not in b.refs()      # 乙不知情，不进画像
    assert "m.2" not in a.refs()            # 别人的经历不进你的画像
    assert "m.1" not in b.refs()


def test_budget_cuts_may_before_should_and_never_must(tmp_path):
    mem, _ = _stores(tmp_path)
    mem.append(_mem("m.must", "global", "要害" * 20, 0.95))
    mem.append(_mem("m.should", "global", "次要" * 20, 0.6))
    mem.append(_mem("m.may", "global", "边角" * 20, 0.1))
    asm = Assembler()

    tight = asm.assemble(
        node="planner", chapter=5, mem_store=mem, budget_tokens=45
    )
    assert "m.must" in tight.refs()
    assert "m.may" not in tight.refs()

    loose = asm.assemble(node="planner", chapter=5, mem_store=mem, budget_tokens=4000)
    assert set(loose.refs()) == {"m.must", "m.should", "m.may"}


def test_critic_profile_carries_cognition_map(tmp_path):
    mem, arc = _stores(tmp_path)
    mem.append(_mem("m.1", "global", "宗门大比在即", 0.7))
    arc.append(
        ArcRecord(id="sec.s", kind="secret", state="PLANTED", desc="身世",
                  knowledge=[Knowledge(char="char.a", since_ch=3)])
    )
    ctx = Assembler().assemble(
        node="continuity-critic", chapter=5, mem_store=mem, arc_store=arc,
        cast=["char.a", "char.b"],
    )
    assert ctx.cognition == {"char.a": ["sec.s"], "char.b": []}
    assert "sec.s" in ctx.refs()  # 宽画像不按单角色收窄


def test_empty_store_and_non_character_owner(tmp_path):
    mem, arc = _stores(tmp_path)
    asm = Assembler()
    assert asm.assemble(node="character", chapter=1, mem_store=mem, arc_store=arc, char="char.a").facts() == []
    assert asm.known_facts(char="ENV", chapter=1, mem_store=mem) == []


def test_unknown_profile_raises(tmp_path):
    mem, _ = _stores(tmp_path)
    with pytest.raises(ValueError):
        Assembler().assemble(node="extractor", chapter=1, mem_store=mem)
