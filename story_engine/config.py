"""运行配置 —— 一律走环境变量 / `.env`（pydantic-settings，前缀 `STORY_`）。

见仓库根目录 `.env.example`。代码里不要硬编码 api key 或模型名覆盖；
默认值仅作本地 UT 兜底（`llm_provider=mock`）。
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="STORY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: str = "./data"           # store JSONL 落地目录
    telemetry_path: str = "./data/runs.jsonl"

    # LLM（默认 Mock 保 UT 零成本；真跑：STORY_LLM_PROVIDER=openai + STORY_OPENAI_API_KEY）
    # M2 选型：DeepSeek deepseek-v4-pro，走 OpenAI 兼容端点 + instructor 结构化输出。
    llm_provider: str = "mock"         # mock | openai（OpenAI 兼容端点，含 DeepSeek）
    llm_model: str = "deepseek-v4-pro"
    llm_max_retries: int = 2
    # per-node 覆盖（JSON）。权威默认档在 llm/node_profiles.py；此处只覆盖。
    # 一键可查：uv run python -m story_engine.llm
    # STORY_LLM_NODE_MODELS={"character":"deepseek-v4-flash"}
    llm_node_models: dict[str, str] = Field(default_factory=dict)
    # STORY_LLM_NODE_THINKING={"planner":"enabled","character":"disabled"}
    # 取值：enabled | disabled | inherit（不传，跟 API 默认）
    llm_node_thinking: dict[str, str] = Field(default_factory=dict)
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.deepseek.com"

    genesis_max_iter: int = 3

    # Embedder（M4b；默认 fake 保 UT 零成本）
    embedder_provider: str = "fake"    # fake | openai
    embedder_model: str = "text-embedding-3-small"
    embedder_dim: int = 64             # FakeEmbedder 维度


def load_settings() -> Settings:
    return Settings()
