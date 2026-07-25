"""LLM provider 抽象 + 统一客户端。

LLMClient.complete_structured(prompt, response_model) -> pydantic 实例：
  内置重试、结构化输出校验、成本记账（写 RunRecord）。
provider 可换：OpenAI-compatible / Mock（测试用）。
"""

from __future__ import annotations

import time
from typing import Protocol, TypeVar

from pydantic import BaseModel

from story_engine.telemetry.runrecord import RunRecord, Telemetry

T = TypeVar("T", bound=BaseModel)


class Completion(BaseModel):
    """provider 原始返回。"""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = "unknown"


class LLMProvider(Protocol):
    def complete(self, prompt: str, **cfg: object) -> Completion:
        ...


# 粗略计价（USD / 1K token），M0 占位，真实价按 provider 配。
_PRICE_PER_1K = {"prompt": 0.0005, "completion": 0.0015}


def _estimate_cost(prompt_tokens: int, completion_tokens: int) -> float:
    return (
        prompt_tokens / 1000 * _PRICE_PER_1K["prompt"]
        + completion_tokens / 1000 * _PRICE_PER_1K["completion"]
    )


class LLMClient:
    def __init__(
        self,
        provider: LLMProvider,
        telemetry: Telemetry | None = None,
        max_retries: int = 2,
    ) -> None:
        self._provider = provider
        self._telemetry = telemetry
        self._max_retries = max_retries

    def complete_structured(
        self,
        prompt: str,
        response_model: type[T],
        *,
        node: str = "unknown",
        chapter: int | None = None,
        **cfg: object,
    ) -> T:
        """调 provider，把返回文本按 response_model 校验成 pydantic 实例。"""
        last_err: Exception | None = None
        for attempt in range(self._max_retries + 1):
            t0 = time.perf_counter()
            comp = self._provider.complete(prompt, **cfg)
            latency_ms = (time.perf_counter() - t0) * 1000
            try:
                obj = response_model.model_validate_json(comp.text)
                self._log(node, chapter, comp, latency_ms, verdict="PASS")
                return obj
            except Exception as e:  # noqa: BLE001 - 校验失败重试
                last_err = e
                self._log(
                    node, chapter, comp, latency_ms,
                    verdict=f"PARSE_FAIL(attempt={attempt})",
                    note=str(e)[:200],
                )
        raise ValueError(
            f"[{node}] 结构化输出校验失败（重试 {self._max_retries} 次）: {last_err}"
        )

    def _log(
        self,
        node: str,
        chapter: int | None,
        comp: Completion,
        latency_ms: float,
        *,
        verdict: str | None = None,
        note: str | None = None,
    ) -> None:
        if not self._telemetry:
            return
        self._telemetry.record(
            RunRecord(
                node=node,
                chapter=chapter,
                model=comp.model,
                prompt_tokens=comp.prompt_tokens,
                completion_tokens=comp.completion_tokens,
                cost_usd=_estimate_cost(comp.prompt_tokens, comp.completion_tokens),
                latency_ms=latency_ms,
                verdict=verdict,
                note=note,
            )
        )
