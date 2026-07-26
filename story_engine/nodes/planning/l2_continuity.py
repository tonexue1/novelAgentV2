"""L2 章事件链连续性硬检（确定性，不靠文案警察）。

校验 inherits/leaves_open 接力图与 spine 锚点覆盖；失败由 Architect 重试分章。
"""

from __future__ import annotations

import math

from story_engine.schemas.stores.plan import L2

# 章 inherits 可引用的卷脊骨标签（与 VolumeSpine 字段对应）
SPINE_HOOKS = frozenset({
    "shared_pressure",
    "inciting",
    "midpoint",
    "climax",
    "spine.shared_pressure",
    "spine.inciting",
    "spine.midpoint",
    "spine.climax",
})

_REQUIRED_TOUCHES = frozenset({"inciting", "midpoint", "climax"})


class L2ContinuityError(ValueError):
    """章事件链不连续或脊骨覆盖不足。"""


def assert_l2_continuity(l2: L2, *, inciting_max_ratio: float = 0.4) -> None:
    """失败抛 L2ContinuityError；通过则静默返回。"""
    errors: list[str] = []
    beats = list(l2.chapter_beats)
    if not beats:
        raise L2ContinuityError("chapter_beats 为空")
    if l2.volume_spine is None:
        raise L2ContinuityError("缺少 volume_spine")

    open_pool: set[str] = set(SPINE_HOOKS)
    touches: set[str] = set()
    n = len(beats)

    for i, beat in enumerate(beats):
        seq = beat.planned_seq
        inherits = [h.strip() for h in beat.inherits if h and h.strip()]
        leaves = [h.strip() for h in beat.leaves_open if h and h.strip()]

        if i == 0:
            for h in inherits:
                if h not in open_pool:
                    errors.append(f"第 {seq} 章 inherits 无法解析: {h!r}")
        else:
            if not inherits:
                errors.append(f"第 {seq} 章 inherits 为空（须接住前序钩子）")
            for h in inherits:
                if h not in open_pool:
                    errors.append(f"第 {seq} 章 inherits 无法解析: {h!r}")

            prev = beats[i - 1]
            prev_pov = {p for p in prev.pov_focus if p}
            cur_pov = {p for p in beat.pov_focus if p}
            if prev_pov and cur_pov and prev_pov.isdisjoint(cur_pov):
                prev_leaves = {h.strip() for h in prev.leaves_open if h and h.strip()}
                if not prev_leaves.intersection(inherits):
                    errors.append(
                        f"第 {seq} 章与上一章 POV 不相交，但未继承上一章 leaves_open"
                    )

        if not leaves:
            errors.append(f"第 {seq} 章 leaves_open 为空")
        open_pool.update(leaves)
        touches.add(beat.touches_spine)

    missing = _REQUIRED_TOUCHES - touches
    if missing:
        errors.append(f"touches_spine 缺少: {sorted(missing)}")

    inciting_seqs = [b.planned_seq for b in beats if b.touches_spine == "inciting"]
    if inciting_seqs:
        deadline = max(1, math.ceil(n * inciting_max_ratio))
        if min(inciting_seqs) > deadline:
            errors.append(
                f"inciting 落在第 {min(inciting_seqs)} 章，超过前 {deadline}/{n} 章窗口"
            )

    if errors:
        raise L2ContinuityError("; ".join(errors))
