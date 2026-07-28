"""E1/E2：成本与延迟 —— 聚合 RunRecord。"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, Field

from story_engine.telemetry.runrecord import RunRecord


class BucketStats(BaseModel):
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms_sum: float = 0.0
    latency_ms_mean: float = 0.0


class EMetrics(BaseModel):
    available: bool = False
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms_sum: float = 0.0
    latency_ms_mean: float = 0.0
    by_node: dict[str, BucketStats] = Field(default_factory=dict)
    by_model: dict[str, BucketStats] = Field(default_factory=dict)
    verdict_counts: dict[str, int] = Field(default_factory=dict)


def _accumulate(bucket: BucketStats, r: RunRecord) -> None:
    bucket.calls += 1
    bucket.prompt_tokens += r.prompt_tokens
    bucket.completion_tokens += r.completion_tokens
    bucket.total_tokens += r.total_tokens
    bucket.cost_usd += r.cost_usd
    bucket.latency_ms_sum += r.latency_ms


def _finalize(bucket: BucketStats) -> None:
    if bucket.calls:
        bucket.latency_ms_mean = round(bucket.latency_ms_sum / bucket.calls, 2)
        bucket.cost_usd = round(bucket.cost_usd, 6)


def compute_e(records: list[RunRecord] | None, *, available: bool) -> EMetrics:
    if not available:
        return EMetrics(available=False)
    records = records or []
    by_node: dict[str, BucketStats] = defaultdict(BucketStats)
    by_model: dict[str, BucketStats] = defaultdict(BucketStats)
    verdicts: dict[str, int] = {}
    total = BucketStats()
    for r in records:
        _accumulate(total, r)
        _accumulate(by_node[r.node], r)
        model_key = r.model or "(none)"
        _accumulate(by_model[model_key], r)
        if r.verdict:
            verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
    _finalize(total)
    for b in by_node.values():
        _finalize(b)
    for b in by_model.values():
        _finalize(b)
    return EMetrics(
        available=True,
        calls=total.calls,
        prompt_tokens=total.prompt_tokens,
        completion_tokens=total.completion_tokens,
        total_tokens=total.total_tokens,
        cost_usd=total.cost_usd,
        latency_ms_sum=round(total.latency_ms_sum, 2),
        latency_ms_mean=total.latency_ms_mean,
        by_node=dict(sorted(by_node.items())),
        by_model=dict(sorted(by_model.items())),
        verdict_counts=verdicts,
    )
