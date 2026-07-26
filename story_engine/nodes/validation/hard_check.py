"""Hard-Check —— 一致性闸的硬检层（确定性，守 U/B 第一关）。

对应 docs/nodes/validation/hard-check.md + ARCHITECTURE §3.5。
每条规则是纯函数，返回 list[Violation]。两个检点：

**条目级 / 章级**（M1）
  ① evidence 可解析：每个 EvidenceSpan 必须落到已提交 ScriptStore 位置（BLOCK）。
  ② 修为单调：角色 ability 台阶 as-of 非降，无解释不倒退（BLOCK）。
  ③ secret 边界：引用了自己被 hidden_from 的 secret（CORRECT）。

**逐拍即时**（Character 每产一拍后，修复=只重调该拍）
  owner 在场 / hits 指向真实承重拍 / prose 里的实体 id 存在 / secret 认知边界 / 能力不越级。

**场收束**（场级，随后交 Continuity Critic）
  地点在册 / POV 在场 / FULFILL 前必有 PLANT / 时间线不倒流 / 承重拍履约。
"""

from __future__ import annotations

import re

from story_engine.primitives.enums import Severity
from story_engine.primitives.evidence import EvidenceSpan
from story_engine.primitives.ids import mint_violation_id
from story_engine.schemas.stores.script import NON_CHARACTER_OWNERS
from story_engine.schemas.stores.violation import (
    Category,
    Locus,
    Stage,
    Violation,
)


def make_violation(
    *,
    rule: str,
    category: Category,
    severity: Severity,
    message: str,
    chapter: int,
    stage: Stage = "character",
    locus: Locus | None = None,
    script_evidence: list[EvidenceSpan] | None = None,
    refs: list[str] | None = None,
    escalation_level: str = "beat",
) -> Violation:
    """硬检违规构造口子。规则名不占字段，前缀进 message 保持可 grep。"""
    return Violation(
        id=mint_violation_id(),
        chapter=chapter,
        stage=stage,
        check_type="hard",
        severity=severity,
        category=category,
        locus=locus,
        script_evidence=list(script_evidence or []),
        refs=list(refs or []),
        message=f"[{rule}] {message}",
        escalation_level=escalation_level,  # type: ignore[arg-type]
    )


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
                item_id = getattr(it, "id", None)
                out.append(
                    make_violation(
                        rule="evidence_resolvable",
                        category="ref_integrity",
                        severity=Severity.BLOCK,
                        message=f"evidence {span.to_str()} 无法解析到已提交 ScriptStore 位置",
                        chapter=chapter,
                        script_evidence=[span],
                        refs=[item_id] if item_id else [],
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
                make_violation(
                    rule="ability_monotonic",
                    category="ability",
                    severity=Severity.BLOCK,
                    message=(
                        f"{scope} 修为倒退：第 {m.t_valid} 章 rank={m.ability_rank} "
                        f"< 此前 rank={peak}（{peak_ref}）"
                    ),
                    chapter=chapter,
                    script_evidence=list(m.evidence),
                    refs=[scope, m.id],
                )
            )
        else:
            peak = m.ability_rank
            peak_ref = m.id
    return out


def check_secret_boundary(
    char_id: str,
    referenced_arc_ids: list[str],
    arc_store,
    *,
    chapter: int,
    locus: Locus | None = None,
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
                make_violation(
                    rule="secret_boundary",
                    category="POV",
                    severity=Severity.CORRECT,
                    message=f"{char_id} 触及第 {chapter} 章尚未知情的 secret {aid}（认知边界穿帮）",
                    chapter=chapter,
                    locus=locus,
                    refs=[char_id, aid],
                )
            )
    return out


# ── 逐拍即时（Character 每产一拍后）──────────────────────────
_ARC_PREFIXES = ("fs", "th", "sec")
_WORLD_PREFIXES = ("loc", "org", "item", "art", "concept", "race")
_ID_IN_TEXT = re.compile(rf"(?:{'|'.join(_ARC_PREFIXES + _WORLD_PREFIXES)})\.[a-z0-9_]+")


def ids_in_text(*texts: str | None) -> list[str]:
    """抽 prose/派工里字面出现的实体 id（正则只认 id 形，不猜自然语言）。"""
    seen: list[str] = []
    for t in texts:
        for m in _ID_IN_TEXT.finditer(t or ""):
            if m.group(0) not in seen:
                seen.append(m.group(0))
    return seen


def build_ability_ladder(mem_store) -> dict[str, int]:
    """从 ability 记忆反推台阶表（term → rank）。

    真正的 ladder 该由 WorldStore 给（M4 补字段）；在那之前只有带 ability_rank 的
    记忆条目是可信来源，没有就退化成空表 = 本规则静默不跑，不臆造越级。
    """
    ladder: dict[str, int] = {}
    for m in mem_store.all():
        if getattr(m, "type", None) == "ability" and getattr(m, "ability_rank", None) is not None:
            term = (m.text or "").strip()
            if term:
                ladder[term] = max(ladder.get(term, 0), m.ability_rank)
    return ladder


def check_beat(
    beat,
    *,
    contract,
    chapter: int,
    arc_store=None,
    world_ids: set[str] | None = None,
    mem_store=None,
    ability_ladder: dict[str, int] | None = None,
) -> list[Violation]:
    """逐拍即时硬检。违规的修复范围就是这一拍——只重调它，不动整场。"""
    locus = Locus(
        chapter=f"c{chapter}",
        scene=contract.scene_id,
        beat=beat.beat_id if beat.beat_id != "tmp" else None,
        obligation=beat.hits,
    )
    text = beat.as_text()
    out: list[Violation] = []

    # ① owner 在场：不在 cast 里的人不许上台（死人说话的近似判定）
    cast = {c.char for c in contract.cast}
    if beat.owner not in cast and beat.owner not in NON_CHARACTER_OWNERS:
        out.append(
            make_violation(
                rule="beat_owner_present",
                category="alive_present",
                severity=Severity.BLOCK,
                message=f"{beat.owner} 不在本场 cast（{sorted(cast)}）却演了一拍",
                chapter=chapter,
                stage="director·dispatch",
                locus=locus,
                refs=[beat.owner],
            )
        )

    # ② hits 指向真实承重拍
    ob_ids = {o.obligation_id for o in contract.obligations}
    if beat.hits and beat.hits not in ob_ids:
        out.append(
            make_violation(
                rule="beat_hits_valid",
                category="ref_integrity",
                severity=Severity.CORRECT,
                message=f"hits={beat.hits} 不是本场承重拍（{sorted(ob_ids)}）",
                chapter=chapter,
                stage="director·dispatch",
                locus=locus,
                refs=[beat.hits],
            )
        )

    # ③ 引用 id 存在：prose 里字面写出的 id 必须在册
    mentioned = ids_in_text(text, beat.dramatic_goal)
    for eid in mentioned:
        prefix = eid.split(".", 1)[0]
        if prefix in _ARC_PREFIXES:
            known = arc_store is not None and arc_store.get(eid) is not None
        else:
            known = world_ids is not None and eid in world_ids
        if not known:
            out.append(
                make_violation(
                    rule="beat_ref_integrity",
                    category="ref_integrity",
                    severity=Severity.CORRECT,
                    message=f"引用了不存在的实体 {eid}",
                    chapter=chapter,
                    locus=locus,
                    refs=[eid],
                )
            )

    # ④ secret 认知边界
    if arc_store is not None and beat.owner not in NON_CHARACTER_OWNERS:
        secrets = [e for e in mentioned if e.startswith("sec.")]
        out.extend(
            check_secret_boundary(beat.owner, secrets, arc_store, chapter=chapter, locus=locus)
        )

    # ⑤ 能力不越级：说出/使出高于 as-of 台阶的境界
    ladder = ability_ladder
    if ladder is None and mem_store is not None:
        ladder = build_ability_ladder(mem_store)
    if ladder and mem_store is not None and beat.owner not in NON_CHARACTER_OWNERS:
        out.extend(
            _check_ability_ceiling(
                beat.owner, text, ladder, mem_store, chapter=chapter, locus=locus
            )
        )
    return out


def _check_ability_ceiling(
    char_id: str,
    text: str,
    ladder: dict[str, int],
    mem_store,
    *,
    chapter: int,
    locus: Locus | None,
) -> list[Violation]:
    ranks = [
        m.ability_rank
        for m in mem_store.as_of(chapter, scope=char_id, type="ability")
        if m.ability_rank is not None
    ]
    current = max(ranks) if ranks else None
    if current is None:
        return []  # 没有 as-of 台阶就没有天花板可越
    out: list[Violation] = []
    for term, rank in ladder.items():
        if rank > current and term in text:
            out.append(
                make_violation(
                    rule="beat_ability_ceiling",
                    category="ability",
                    severity=Severity.BLOCK,
                    message=f"{char_id} 当前台阶 rank={current}，本拍却动用了 {term}(rank={rank})",
                    chapter=chapter,
                    locus=locus,
                    refs=[char_id],
                )
            )
    return out


# ── 场收束（整场落定后，随后交 Critic）───────────────────────
_FS_PLANTED_STATES = frozenset({"PLANTED", "REINFORCED"})


def check_scene(
    scene,
    *,
    contract,
    chapter: int,
    arc_store=None,
    world_ids: set[str] | None = None,
    previous_scenes: list | None = None,
) -> list[Violation]:
    """场级硬检。修复范围是整场——重导 setup 或同场重跑。"""
    locus = Locus(chapter=f"c{chapter}", scene=scene.scene_id)
    out: list[Violation] = []

    # ① 地点在册
    #    WorldStore 目前不吸收涌现地点（WorldOp 未落库，M4），此时把"不在册"
    #    当 CORRECT 会把每一场都拖进重导。先记 ADVISORY，等 WorldOp 接上再升级。
    if world_ids and scene.location not in world_ids:
        out.append(
            make_violation(
                rule="scene_location_exists",
                category="location",
                severity=Severity.ADVISORY,
                message=f"地点 {scene.location} 不在 WorldStore 在册 canon 里",
                chapter=chapter,
                stage="director·setup",
                locus=locus,
                refs=[scene.location],
                escalation_level="scene",
            )
        )

    # ② POV 在场
    cast = {c.char for c in scene.cast}
    if scene.pov not in cast:
        out.append(
            make_violation(
                rule="scene_pov_present",
                category="POV",
                severity=Severity.CORRECT,
                message=f"POV {scene.pov} 不在本场 cast（{sorted(cast)}）",
                chapter=chapter,
                stage="director·setup",
                locus=locus,
                refs=[scene.pov],
                escalation_level="scene",
            )
        )

    # ③ 伏笔 FULFILL 前必有 PLANT
    if arc_store is not None:
        for ob in contract.obligations:
            binds = ob.binds
            if binds is None or binds.op != "FULFILL":
                continue
            rec = arc_store.get(binds.fs_id)
            state = getattr(rec, "state", None) if rec is not None else None
            if state not in _FS_PLANTED_STATES:
                out.append(
                    make_violation(
                        rule="scene_foreshadow_order",
                        category="foreshadow_order",
                        severity=Severity.CORRECT,
                        message=(
                            f"承重拍 {ob.obligation_id} 要收 {binds.fs_id}，"
                            f"但它 as-of 状态是 {state or '不存在'}（未 PLANT 不能 FULFILL）"
                        ),
                        chapter=chapter,
                        stage="director·setup",
                        locus=Locus(
                            chapter=f"c{chapter}",
                            scene=scene.scene_id,
                            obligation=ob.obligation_id,
                        ),
                        refs=[binds.fs_id],
                        escalation_level="scene",
                    )
                )

    # ④ 时间线不倒流（day 缺省则不判）
    day = scene.time.day if scene.time else None
    if day is not None:
        for prev in previous_scenes or []:
            prev_day = prev.time.day if prev.time else None
            if prev_day is not None and day < prev_day:
                out.append(
                    make_violation(
                        rule="scene_timeline",
                        category="timeline",
                        severity=Severity.BLOCK,
                        message=f"本场 day={day} 早于同章前场 {prev.scene_id} 的 day={prev_day}",
                        chapter=chapter,
                        stage="director·setup",
                        locus=locus,
                        escalation_level="scene",
                    )
                )
                break

    # ⑤ 承重拍履约（撞 budget 强制收场会漏锚）
    hit = {b.hits for b in scene.beats if b.hits}
    missed = [o.obligation_id for o in contract.obligations if o.obligation_id not in hit]
    if missed:
        out.append(
            make_violation(
                rule="scene_obligations_covered",
                category="logic",
                severity=Severity.ADVISORY,
                message=f"本场收束时仍有承重拍未命中: {missed}",
                chapter=chapter,
                locus=locus,
                refs=missed,
                escalation_level="scene",
            )
        )
    return out
