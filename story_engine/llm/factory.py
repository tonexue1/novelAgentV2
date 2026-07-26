"""按 Settings 组装 LLMClient（provider 选择的唯一入口）。"""

from __future__ import annotations

from story_engine.config import Settings, load_settings
from story_engine.llm.base import LLMClient, LLMProvider
from story_engine.llm.mock import MockProvider
from story_engine.telemetry.runrecord import Telemetry


def build_llm_client(
    settings: Settings | None = None,
    telemetry: Telemetry | None = None,
) -> LLMClient:
    s = settings or load_settings()
    provider: LLMProvider
    if s.llm_provider == "mock":
        provider = MockProvider()
    elif s.llm_provider == "openai":
        from story_engine.llm.openai_provider import OpenAIProvider

        provider = OpenAIProvider(
            api_key=s.openai_api_key or "",
            base_url=s.openai_base_url,
            model=s.llm_model,
            max_retries=s.llm_max_retries,
        )
    else:
        raise ValueError(f"未知 llm_provider: {s.llm_provider}（可选 mock | openai）")
    return LLMClient(
        provider,
        telemetry=telemetry,
        max_retries=s.llm_max_retries,
        node_models=s.llm_node_models,
    )
