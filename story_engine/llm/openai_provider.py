"""OpenAI 兼容端点 provider（M2 选型：DeepSeek `deepseek-v4-pro`）。

结构化输出双层兜底（DeepSeek 不支持 strict json_schema，只有 json_object）：
  1. 服务端 `response_format={"type": "json_object"}` 保 JSON 语法合法（instructor Mode.JSON 自动设置）；
  2. instructor 在应用层注入 schema、解析、校验失败时把 Pydantic 报错回喂模型自修复重试。

DeepSeek 适配点：
  - json_object 模式要求 prompt 含 "json" 字样——instructor 注入的 schema 系统消息天然满足；
  - 输出被 max_tokens 截断（finish_reason=length）时给出明确报错，不与解析失败混淆；
  - 偶发空 content 落入 instructor 重试路径。

留痕注意：instructor 内部重试的中间尝试不产生独立 RunRecord，
最终返回的 usage 只反映最后一次成功调用（M2 接受，M5 评估期如需精确记账再改）。
"""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel

from story_engine.llm.base import Completion

T = TypeVar("T", bound=BaseModel)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"


def _to_completion(raw: object, model: str) -> Completion:
    """openai SDK 的 ChatCompletion → 本项目 Completion（usage 缺失时置 0）。"""
    usage = getattr(raw, "usage", None)
    choices = getattr(raw, "choices", None) or []
    text = ""
    if choices:
        text = getattr(getattr(choices[0], "message", None), "content", None) or ""
    return Completion(
        text=text,
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        model=getattr(raw, "model", None) or model,
    )


class OpenAIProvider:
    """OpenAI 兼容 chat.completions provider，结构化输出走 instructor。

    满足 LLMProvider 协议（complete），并额外提供 complete_structured
    （LLMClient 检测到即委托，见 llm/base.py）。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = "deepseek-v4-pro",
        max_retries: int = 2,
        temperature: float | None = None,
    ) -> None:
        import instructor
        from openai import OpenAI

        if not api_key:
            raise ValueError("OpenAIProvider 需要 api_key（STORY_OPENAI_API_KEY）")
        self.model = model
        self._max_retries = max_retries
        self._temperature = temperature
        self._raw = OpenAI(api_key=api_key, base_url=base_url)
        # Mode.JSON：response_format=json_object + schema 注入 system 消息，
        # 适配 DeepSeek（不支持 json_schema；prompt 需含 "json"，注入消息天然满足）。
        self._structured = instructor.from_openai(self._raw, mode=instructor.Mode.JSON)

    # ── 纯文本（Writer 散文等非结构化场合）─────────────────────────
    def complete(self, prompt: str, **cfg: object) -> Completion:
        params = self._params(cfg)
        raw = self._raw.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            **params,
        )
        self._guard_truncation(raw)
        return _to_completion(raw, str(params["model"]))

    # ── 结构化（生产层节点主路径）──────────────────────────────────
    def complete_structured(
        self,
        prompt: str,
        response_model: type[T],
        **cfg: object,
    ) -> tuple[T, Completion]:
        params = self._params(cfg)
        try:
            obj, raw = self._structured.chat.completions.create_with_completion(
                messages=[{"role": "user", "content": prompt}],
                response_model=response_model,
                max_retries=self._max_retries,
                **params,
            )
        except Exception as e:
            self._reraise_if_truncated(e)
            raise
        return obj, _to_completion(raw, str(params["model"]))

    # ── 内部 ──────────────────────────────────────────────────────
    def _params(self, cfg: dict[str, object]) -> dict[str, object]:
        params = dict(cfg)
        params.setdefault("model", self.model)
        if self._temperature is not None:
            params.setdefault("temperature", self._temperature)
        return params

    @staticmethod
    def _finish_reason(raw: object) -> str | None:
        choices = getattr(raw, "choices", None) or []
        return getattr(choices[0], "finish_reason", None) if choices else None

    def _guard_truncation(self, raw: object) -> None:
        if self._finish_reason(raw) == "length":
            raise ValueError(
                "LLM 输出被 max_tokens 截断（finish_reason=length），请调大 max_tokens"
            )

    def _reraise_if_truncated(self, e: Exception) -> None:
        """instructor 重试耗尽时，若末次输出是截断导致的解析失败，换成明确报错。"""
        last = getattr(e, "last_completion", None)
        if last is not None and self._finish_reason(last) == "length":
            raise ValueError(
                "LLM 结构化输出被 max_tokens 截断（finish_reason=length），"
                "请调大 max_tokens 而非重试"
            ) from e
