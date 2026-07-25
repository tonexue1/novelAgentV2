"""RunRecord：每次节点 / LLM 调用的留痕。

这是评估 harness 的地基（见 docs/EVALUATION.md「留痕即评估地基」）：
  - E 组成本 / 延迟指标直接从 RunRecord 聚合；
  - D2 升级阶梯统计从 verdict 聚合。
M0 就把这根桩打进去，后面评估白捡。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel, Field


class RunRecord(BaseModel):
    node: str                          # 谁：architect / retriever / ...
    ts: float = Field(default_factory=time.time)
    chapter: int | None = None         # as-of 上下文
    model: str | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    verdict: str | None = None         # PASS / BLOCK / REITERATE / ...
    note: str | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class Telemetry:
    """收集 RunRecord，落 JSONL，并提供简单聚合（E / D2 指标雏形）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self._records: list[RunRecord] = []
        self._path = Path(path) if path else None
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, rec: RunRecord) -> None:
        self._records.append(rec)
        if self._path:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(rec.model_dump_json() + "\n")

    def all(self) -> list[RunRecord]:
        return list(self._records)

    # ── 聚合雏形 ──────────────────────────────────────────────
    def total_cost(self) -> float:
        return sum(r.cost_usd for r in self._records)

    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self._records)

    def verdict_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self._records:
            if r.verdict:
                counts[r.verdict] = counts.get(r.verdict, 0) + 1
        return counts

    def summary(self) -> str:
        return json.dumps(
            {
                "calls": len(self._records),
                "total_tokens": self.total_tokens(),
                "total_cost_usd": round(self.total_cost(), 6),
                "verdicts": self.verdict_counts(),
            },
            ensure_ascii=False,
        )
