"""OpenAIProvider / 结构化委托 / 工厂——不打真实网络。"""

from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from story_engine.config import Settings
from story_engine.llm.base import Completion, LLMClient
from story_engine.llm.factory import build_llm_client
from story_engine.llm.mock import MockProvider
from story_engine.llm.openai_provider import OpenAIProvider, _to_completion
from story_engine.telemetry.runrecord import Telemetry


class Answer(BaseModel):
    verdict: str
    score: int


class FakeStructuredProvider:
    """自带 complete_structured 的 provider——验证 LLMClient 委托分支。"""

    model = "fake-structured"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def complete(self, prompt: str, **cfg: object) -> Completion:
        raise AssertionError("委托路径不应回落到 complete")

    def complete_structured(self, prompt, response_model, **cfg):
        self.calls.append({"prompt": prompt, "cfg": cfg})
        obj = response_model(verdict="PASS", score=9)
        comp = Completion(
            text=obj.model_dump_json(), prompt_tokens=10,
            completion_tokens=5, model=str(cfg.get("model", self.model)),
        )
        return obj, comp


def test_client_delegates_to_structured_provider():
    provider = FakeStructuredProvider()
    tel = Telemetry()
    client = LLMClient(provider, telemetry=tel)

    ans = client.complete_structured("judge json", Answer, node="critic", chapter=2)
    assert ans.verdict == "PASS" and ans.score == 9
    assert len(provider.calls) == 1

    recs = tel.all()
    assert len(recs) == 1
    assert recs[0].verdict == "PASS"
    assert recs[0].total_tokens == 15


def test_node_model_override_reaches_provider():
    provider = FakeStructuredProvider()
    client = LLMClient(provider, node_models={"writer": "kimi-k3"})

    client.complete_structured("x", Answer, node="writer")
    client.complete_structured("x", Answer, node="planner")
    assert provider.calls[0]["cfg"].get("model") == "kimi-k3"
    assert "model" not in provider.calls[1]["cfg"]


def test_structured_failure_logged_and_raised():
    class BoomProvider(FakeStructuredProvider):
        def complete_structured(self, prompt, response_model, **cfg):
            raise RuntimeError("boom")

    tel = Telemetry()
    client = LLMClient(BoomProvider(), telemetry=tel)
    with pytest.raises(RuntimeError):
        client.complete_structured("x", Answer, node="critic")
    recs = tel.all()
    assert len(recs) == 1
    assert recs[0].verdict == "STRUCTURED_FAIL"


def test_mock_provider_still_uses_parse_loop():
    provider = MockProvider(default_json='{"verdict": "PASS", "score": 1}')
    client = LLMClient(provider)
    ans = client.complete_structured("x", Answer, node="n")
    assert ans.score == 1


def test_to_completion_maps_usage_and_handles_missing():
    raw = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=7, completion_tokens=3),
        choices=[SimpleNamespace(message=SimpleNamespace(content="hi"),
                                 finish_reason="stop")],
        model="deepseek-v4-pro",
    )
    comp = _to_completion(raw, "fallback")
    assert comp.prompt_tokens == 7 and comp.completion_tokens == 3
    assert comp.text == "hi" and comp.model == "deepseek-v4-pro"

    empty = SimpleNamespace(usage=None, choices=[], model=None)
    comp2 = _to_completion(empty, "fallback")
    assert comp2.text == "" and comp2.model == "fallback"


def test_openai_provider_requires_api_key():
    with pytest.raises(ValueError, match="api_key"):
        OpenAIProvider(api_key="")


def test_truncation_guard():
    provider = OpenAIProvider(api_key="sk-test")
    truncated = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="{"),
                                 finish_reason="length")],
    )
    with pytest.raises(ValueError, match="max_tokens"):
        provider._guard_truncation(truncated)


def test_factory_mock_default_and_unknown_provider():
    client = build_llm_client(Settings(llm_provider="mock"))
    assert isinstance(client, LLMClient)

    with pytest.raises(ValueError, match="llm_provider"):
        build_llm_client(Settings(llm_provider="nope"))


def test_factory_openai_requires_key():
    with pytest.raises(ValueError, match="api_key"):
        build_llm_client(Settings(llm_provider="openai", openai_api_key=None))
