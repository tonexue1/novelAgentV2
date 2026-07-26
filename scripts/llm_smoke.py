"""真实 LLM 端点冒烟（手动跑，不进 pytest）。

用法：
  1. .env 里配 STORY_LLM_PROVIDER=openai、STORY_OPENAI_API_KEY=sk-...
     （base_url/model 默认 DeepSeek deepseek-v4-pro，可覆盖）
  2. uv run python scripts/llm_smoke.py

验证三件事：结构化输出解析成功、成本记账落 RunRecord、telemetry 汇总可读。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from story_engine.config import load_settings
from story_engine.llm.factory import build_llm_client
from story_engine.telemetry.runrecord import Telemetry


class SceneIdea(BaseModel):
    """冒烟用最小结构化产物。"""

    title: str = Field(description="场景标题")
    location: str = Field(description="发生地点")
    conflict: str = Field(description="一句话冲突")
    beats: list[str] = Field(description="3 个关键拍", min_length=3, max_length=3)


def main() -> None:
    settings = load_settings()
    if settings.llm_provider != "openai":
        raise SystemExit(
            "请在 .env 设 STORY_LLM_PROVIDER=openai + STORY_OPENAI_API_KEY 后再跑"
        )
    tel = Telemetry(settings.telemetry_path)
    client = build_llm_client(settings, telemetry=tel)

    idea = client.complete_structured(
        "为一部东方玄幻小说构思一个开篇场景（中文，输出 JSON）。",
        SceneIdea,
        node="smoke",
        chapter=0,
    )
    print("── 结构化产物 ──")
    print(idea.model_dump_json(indent=2))
    print("── telemetry ──")
    print(tel.summary())


if __name__ == "__main__":
    main()
