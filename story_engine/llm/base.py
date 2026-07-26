"""LLM provider 抽象 + 统一客户端。

LLMClient.complete_structured(prompt, response_model) -> pydantic 实例：
  内置重试、结构化输出校验、成本记账（写 RunRecord）。
provider 可换：OpenAI-compatible / Mock（测试用）。
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Protocol, TypeVar

from pydantic import BaseModel

from story_engine.telemetry.runrecord import RunRecord, Telemetry

T = TypeVar("T", bound=BaseModel)

# (node, prompt) → 走查脚本可用来落盘上下文
PromptHook = Callable[[str, str], None]


class Completion(BaseModel):
    """provider 原始返回。"""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = "unknown"


class LLMProvider(Protocol):
    def complete(self, prompt: str, **cfg: object) -> Completion:
        ...


class StructuredLLMProvider(Protocol):
    """可选扩展：provider 自带结构化输出（schema 注入 + 自修复重试，如 instructor）。

    LLMClient 检测到该方法即委托，不再走手搓 parse 循环。
    """

    def complete_structured(
        self, prompt: str, response_model: type, **cfg: object
    ) -> tuple[object, Completion]:
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
        node_models: dict[str, str] | None = None,
        on_prompt: PromptHook | None = None,
    ) -> None:
        self._provider = provider
        self._telemetry = telemetry
        self._max_retries = max_retries
        # per-node 模型覆盖（M2 选型预留：复杂 schema 节点可单独换模型）
        self._node_models = node_models or {}
        self._on_prompt = on_prompt

    def complete_structured(
        self,
        prompt: str,
        response_model: type[T],
        *,
        node: str = "unknown",
        chapter: int | None = None,
        **cfg: object,
    ) -> T:
        """调 provider，把返回文本按 response_model 校验成 pydantic 实例。

        provider 若自带结构化输出（StructuredLLMProvider，如 OpenAIProvider+instructor）
        则委托之——schema 注入 / 围栏剥离 / 带报错自修复重试都在 provider 层完成；
        否则走下方手搓 parse 循环（Mock / 测试路径）。
        """
        self._emit_prompt(node, prompt)
        if node in self._node_models:
            cfg.setdefault("model", self._node_models[node])

        native = getattr(self._provider, "complete_structured", None)
        if callable(native):
            return self._complete_via_provider(
                native, prompt, response_model, node=node, chapter=chapter, **cfg
            )

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

    def complete_text(
        self,
        prompt: str,
        *,
        node: str = "unknown",
        chapter: int | None = None,
        **cfg: object,
    ) -> str:
        """自由文本生成（只用于消费层成品，如 Writer 散文）。

        生产层节点之间一律走 complete_structured——自然语言只存在于成品和例句里。
        """
        self._emit_prompt(node, prompt)
        if node in self._node_models:
            cfg.setdefault("model", self._node_models[node])
        t0 = time.perf_counter()
        comp = self._provider.complete(prompt, **cfg)
        self._log(node, chapter, comp, (time.perf_counter() - t0) * 1000, verdict="PASS")
        return comp.text

    def _emit_prompt(self, node: str, prompt: str) -> None:
        if self._on_prompt is not None:
            self._on_prompt(node, prompt)

    def _complete_via_provider(
        self,
        native: object,
        prompt: str,
        response_model: type[T],
        *,
        node: str,
        chapter: int | None,
        **cfg: object,
    ) -> T:
        """委托 provider 原生结构化输出，成功/失败均写 RunRecord。"""
        t0 = time.perf_counter()
        try:
            obj, comp = native(prompt, response_model, **cfg)  # type: ignore[operator]
        except Exception as e:
            latency_ms = (time.perf_counter() - t0) * 1000
            self._log(
                node,
                chapter,
                Completion(text="", model=getattr(self._provider, "model", "unknown")),
                latency_ms,
                verdict="STRUCTURED_FAIL",
                note=str(e)[:200],
            )
            raise
        latency_ms = (time.perf_counter() - t0) * 1000
        self._log(node, chapter, comp, latency_ms, verdict="PASS")
        return obj  # type: ignore[return-value]

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
