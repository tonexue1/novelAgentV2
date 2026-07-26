"""LLM 层：provider 抽象 + 统一客户端 + Mock + OpenAI 兼容（DeepSeek）。"""

from story_engine.llm.base import (
    Completion,
    LLMClient,
    LLMProvider,
    StructuredLLMProvider,
)
from story_engine.llm.factory import build_llm_client
from story_engine.llm.mock import CallableProvider, MockProvider

__all__ = [
    "Completion",
    "LLMClient",
    "LLMProvider",
    "StructuredLLMProvider",
    "CallableProvider",
    "MockProvider",
    "build_llm_client",
]
