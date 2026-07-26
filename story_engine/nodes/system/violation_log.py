"""ViolationLog 生命周期 —— 对应 docs/schema/stores/violation-log.md 的两条不变式。

调和「日志 append-only」与「单条 Violation 从 open 追到终态」：
违规对象在编排内存里持有，重试只更新 retry_count / history[]，
**到终态才 append 一次**到日志。日志因此只追加不改写，单条违规仍是一条记录。

重跑硬检会为同一个问题重新铸 id；用指纹去重，命中已在案的就沿用旧对象。
"""

from __future__ import annotations

from collections.abc import Iterable

from story_engine.primitives.enums import Severity
from story_engine.schemas.stores.violation import (
    EscalationLevel,
    EscalationStep,
    ResolutionState,
    Violation,
)

_SEVERITY_ORDER = {Severity.ADVISORY: 0, Severity.CORRECT: 1, Severity.BLOCK: 2}


def worst_severity(violations: Iterable[Violation]) -> Severity | None:
    """取最重的一档；空列表返回 None（= PASS）。"""
    sev = [v.severity for v in violations]
    return max(sev, key=lambda s: _SEVERITY_ORDER[s]) if sev else None


def _fingerprint(v: Violation) -> tuple:
    """同一个问题的稳定标识（id 每次重检都会变，不能用）。"""
    loc = v.locus
    return (
        v.chapter,
        v.stage,
        v.check_type,
        v.category,
        v.message,
        loc.scene if loc else None,
        loc.beat if loc else None,
    )


class ViolationTracker:
    """一章内的违规账本。store 可为 None（不落盘，纯内存跑）。"""

    def __init__(self, store=None) -> None:
        self._store = store
        self._open: dict[tuple, Violation] = {}
        self._settled: list[Violation] = []

    # ── 读 ────────────────────────────────────────────────────
    @property
    def open_violations(self) -> list[Violation]:
        return list(self._open.values())

    @property
    def settled(self) -> list[Violation]:
        return list(self._settled)

    def __len__(self) -> int:
        return len(self._open)

    # ── 写 ────────────────────────────────────────────────────
    def track(self, violations: Iterable[Violation]) -> list[Violation]:
        """登记本轮检出的违规，返回去重后对应的在案对象（新旧混合）。"""
        out: list[Violation] = []
        for v in violations:
            fp = _fingerprint(v)
            existing = self._open.get(fp)
            if existing is None:
                self._open[fp] = v
                out.append(v)
            else:
                out.append(existing)
        return out

    def open_at(self, *, scene: str | None = None, beat: str | None = None) -> list[Violation]:
        """按落点取还开着的违规（重试成功后据此结案）。"""
        out: list[Violation] = []
        for v in self._open.values():
            loc = v.locus
            if beat is not None and (loc is None or loc.beat != beat):
                continue
            if scene is not None and (loc is None or loc.scene != scene):
                continue
            out.append(v)
        return out

    def note_attempt(
        self,
        *,
        level: EscalationLevel,
        outcome: str,
        violations: Iterable[Violation] | None = None,
    ) -> None:
        """记一次阶梯尝试：升级到 level，retry_count+1，history 追一格。"""
        targets = list(violations) if violations is not None else self.open_violations
        for v in targets:
            v.escalation_level = level
            v.retry_count += 1
            v.history = [*v.history, EscalationStep(level=level, attempt=v.retry_count, outcome=outcome)]

    def settle(
        self,
        resolution: ResolutionState,
        *,
        violations: Iterable[Violation] | None = None,
    ) -> list[Violation]:
        """定终态并 flush 到 append-only 日志。"""
        targets = list(violations) if violations is not None else self.open_violations
        flushed: list[Violation] = []
        for v in targets:
            fp = _fingerprint(v)
            self._open.pop(fp, None)
            v.resolution = resolution
            self._settled.append(v)
            flushed.append(v)
            if self._store is not None:
                self._store.append(v)
        return flushed

    def settle_remaining(self, resolution: ResolutionState) -> list[Violation]:
        """章末兜底：还 open 的一律定为 resolution（通常 fixed 或 flagged）。"""
        return self.settle(resolution)
