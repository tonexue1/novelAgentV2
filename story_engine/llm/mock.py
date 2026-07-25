"""MockProvider —— M0 / 测试用，不打真实 LLM。

用法：注册 (关键字 -> 返回 JSON 文本) 的路由；或给一个 default_json。
按 prompt 命中关键字返回对应结构化文本，令 orchestrator 空流程可跑通。
"""

from __future__ import annotations

from collections.abc import Callable

from story_engine.llm.base import Completion


class MockProvider:
    def __init__(
        self,
        routes: dict[str, str] | None = None,
        default_json: str = "{}",
        model: str = "mock",
    ) -> None:
        self._routes = routes or {}
        self._default = default_json
        self._model = model

    def register(self, keyword: str, json_text: str) -> None:
        self._routes[keyword] = json_text

    def complete(self, prompt: str, **cfg: object) -> Completion:
        text = self._default
        for kw, out in self._routes.items():
            if kw in prompt:
                text = out
                break
        return Completion(
            text=text,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            model=self._model,
        )


class CallableProvider:
    """更灵活：用一个函数根据 prompt 生成 JSON 文本。"""

    def __init__(self, fn: Callable[[str], str], model: str = "mock-fn") -> None:
        self._fn = fn
        self._model = model

    def complete(self, prompt: str, **cfg: object) -> Completion:
        text = self._fn(prompt)
        return Completion(
            text=text,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            model=self._model,
        )
