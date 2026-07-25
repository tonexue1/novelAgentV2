"""Hard-Check —— 一致性闸的硬检层（确定性，守 U/B 第一关）。

对应 docs/nodes/validation/hard-check.md + ARCHITECTURE §3.5。
每条规则是纯函数，返回 list[Violation]。M1 落地三条硬红线：
  ① evidence 可解析：每个 EvidenceSpan 必须落到已提交 ScriptStore 位置（BLOCK）。
  ② 修为单调：角色 ability 台阶 as-of 非降，无解释不倒退（BLOCK）。
  ③ secret 边界：引用了自己被 hidden_from 的 secret（CORRECT）。
"""

from __future__ import annotations

from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.primitives.ids import mint_violation_id
from story_engine.schemas.stores.violation import Violation


# ── span 解析 ──────────────────────────────────────────────
def resolve_span(span: EvidenceSpan, script_store) -> bool:
    """span 是否落到已提交 ScriptStore 位置。"""
    chapter = script_store.get(f"c{span.chapter}")
    if chapter is None:
        return False
    if span.scene is None:
        return True  # 整章
    scene_id = f"c{span.chapter}.s{span.scene}"
    scene = next((s for s in chapter.scenes if s.scene_id == scene_id), None)
    if scene is None:
        return False
    if span.beats is None:
        return True  # 整场
    lo, hi = span.beats
    return 1 <= lo <= hi <= len(scene.beats)  # beat 1-indexed，含下界


# ── 规则 ────────────────────────────────────────────────────
def check_evidence_resolvable(items, script_store, *, chapter: int) -> list[Violation]:
    """items：任何带 .evidence 列表的条目（MemoryEntry / ArcRecord …）。"""
    out: list[Violation] = []
    for it in items:
        for span in getattr(it, "evidence", []):
            if not resolve_span(span, script_store):
                out.append(
                    Violation(
                        vio_id=mint_violation_id(),
                        rule="evidence_resolvable",
                        severity=Severity.BLOCK,
                        detail=f"evidence {span.to_str()} 无法解析到已提交 ScriptStore 位置",
                        chapter=chapter,
                        subject=getattr(it, "id", None),
                        evidence=[span],
                    )
                )
    return out


def check_ability_monotonic(mem_store, scope: str, *, chapter: int) -> list[Violation]:
    """角色 ability 台阶随时间非降（as-of chapter，排除未来台阶与软失效条目）。"""
    abilities = [
        m
        for m in mem_store.as_of(chapter, scope=scope, type="ability")
        if m.ability_rank is not None
    ]
    abilities.sort(key=lambda m: m.t_valid)
    out: list[Violation] = []
    peak = None
    peak_ref = None
    for m in abilities:
        if peak is not None and m.ability_rank < peak:
            out.append(
                Violation(
                    vio_id=mint_violation_id(),
                    rule="ability_monotonic",
                    severity=Severity.BLOCK,
                    detail=(
                        f"{scope} 修为倒退：第 {m.t_valid} 章 rank={m.ability_rank} "
                        f"< 此前 rank={peak}（{peak_ref}）"
                    ),
                    chapter=chapter,
                    subject=scope,
                    evidence=list(m.evidence),
                )
            )
        else:
            peak = m.ability_rank
            peak_ref = m.id
    return out


def check_secret_boundary(
    char_id: str, referenced_arc_ids: list[str], arc_store, *, chapter: int
) -> list[Violation]:
    """角色引用/说出了 as-of 本章自己尚不知情的 secret（认知边界穿帮）。

    知情 = knowledge[] 中 char since_ch ≤ chapter；否则视为 hidden（隐式补集）。
    """
    out: list[Violation] = []
    for aid in referenced_arc_ids:
        arc = arc_store.get(aid)
        if arc is None or arc.kind != "secret":
            continue
        if not arc.knows_as_of(char_id, chapter):
            out.append(
                Violation(
                    vio_id=mint_violation_id(),
                    rule="secret_boundary",
                    severity=Severity.CORRECT,
                    detail=f"{char_id} 触及第 {chapter} 章尚未知情的 secret {aid}（认知边界穿帮）",
                    chapter=chapter,
                    subject=aid,
                )
            )
    return out
