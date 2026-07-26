"""节点 LLM 配置表：默认档 + env 覆盖 + Client 注入。"""

from story_engine.llm.base import LLMClient
from story_engine.llm.mock import MockProvider
from story_engine.llm.node_profiles import (
    FAST_MODEL,
    NodeProfileResolver,
    format_roster,
)
from story_engine.telemetry.runrecord import Telemetry


def test_fast_nodes_default_to_flash_no_thinking():
    r = NodeProfileResolver(default_model="deepseek-v4-pro")
    for node in (
        "director_dispatch",
        "character",
        "continuity_critic",
        "faithfulness_check",
        "reconciler",
        "extractor",
    ):
        p = r.resolve(node)
        assert p.model == FAST_MODEL
        assert p.thinking == "disabled"


def test_planner_inherits_thinking_and_default_model():
    r = NodeProfileResolver(default_model="deepseek-v4-pro")
    p = r.resolve("planner")
    assert p.model == "deepseek-v4-pro"
    assert p.thinking == "inherit"


def test_env_overrides():
    r = NodeProfileResolver(
        default_model="deepseek-v4-pro",
        model_overrides={"character": "deepseek-v4-pro"},
        thinking_overrides={"character": "enabled"},
    )
    p = r.resolve("character")
    assert p.model == "deepseek-v4-pro"
    assert p.thinking == "enabled"
    assert p.source == "env_both"


def test_client_applies_profile_into_provider_cfg():
    seen: list[dict] = []

    class Capturing(MockProvider):
        def complete(self, prompt: str, **cfg: object):
            seen.append(dict(cfg))
            return super().complete(prompt, **cfg)

    from pydantic import BaseModel

    class Ans(BaseModel):
        x: int

    tel = Telemetry()
    client = LLMClient(
        Capturing(default_json='{"x":1}'),
        telemetry=tel,
        profile_resolver=NodeProfileResolver(default_model="deepseek-v4-pro"),
    )
    client.complete_structured("hi", Ans, node="character")
    assert seen[0]["model"] == FAST_MODEL
    assert seen[0]["thinking"] == "disabled"
    assert "thinking=disabled" in (tel.all()[0].note or "")


def test_openai_provider_puts_thinking_in_extra_body():
    import pytest

    pytest.importorskip("openai")
    pytest.importorskip("instructor")
    from story_engine.llm.openai_provider import OpenAIProvider

    # 不打真网：只测参数组装
    p = OpenAIProvider(api_key="sk-test", model="deepseek-v4-pro")
    params = p._params({"model": "deepseek-v4-flash", "thinking": "disabled"})
    assert params["model"] == "deepseek-v4-flash"
    assert params["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "thinking" not in params


def test_format_roster_lists_fast_nodes():
    text = format_roster(NodeProfileResolver().roster())
    assert "character" in text and "disabled" in text
