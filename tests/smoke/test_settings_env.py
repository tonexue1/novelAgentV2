"""Settings 从环境变量加载（模型配置走 env）。"""

import json

from story_engine.config import Settings


def test_llm_settings_from_env(monkeypatch):
    monkeypatch.setenv("STORY_LLM_PROVIDER", "openai")
    monkeypatch.setenv("STORY_LLM_MODEL", "deepseek-v4-pro")
    monkeypatch.setenv("STORY_OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("STORY_OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("STORY_LLM_MAX_RETRIES", "3")
    monkeypatch.setenv(
        "STORY_LLM_NODE_MODELS",
        json.dumps({"writer": "kimi-k3", "planner": "deepseek-v4-pro"}),
    )

    s = Settings(_env_file=None)  # 只读进程环境，不读磁盘 .env
    assert s.llm_provider == "openai"
    assert s.llm_model == "deepseek-v4-pro"
    assert s.openai_api_key == "sk-test"
    assert s.openai_base_url == "https://api.deepseek.com"
    assert s.llm_max_retries == 3
    assert s.llm_node_models == {"writer": "kimi-k3", "planner": "deepseek-v4-pro"}


def test_defaults_are_mock_safe(monkeypatch):
    for key in (
        "STORY_LLM_PROVIDER",
        "STORY_LLM_MODEL",
        "STORY_OPENAI_API_KEY",
        "STORY_OPENAI_BASE_URL",
        "STORY_LLM_MAX_RETRIES",
        "STORY_LLM_NODE_MODELS",
    ):
        monkeypatch.delenv(key, raising=False)
    s = Settings(_env_file=None)
    assert s.llm_provider == "mock"
    assert s.llm_model == "deepseek-v4-pro"
    assert s.llm_node_models == {}
