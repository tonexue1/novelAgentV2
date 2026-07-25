"""运行配置 —— pydantic-settings，支持 .env / 环境变量。"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STORY_", env_file=".env", extra="ignore")

    data_dir: str = "./data"           # store JSONL 落地目录
    telemetry_path: str = "./data/runs.jsonl"

    # LLM（M0 默认走 Mock，不需要真实 key）
    llm_provider: str = "mock"         # mock | openai
    llm_model: str = "gpt-4o-mini"
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    genesis_max_iter: int = 3


def load_settings() -> Settings:
    return Settings()
