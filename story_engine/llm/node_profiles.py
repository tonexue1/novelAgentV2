"""节点 LLM 配置表 —— 全局唯一权威源。

查表：
  uv run python -m story_engine.llm
  uv run python -m story_engine.llm --json
  uv run python -m story_engine.llm --node character

规则：
  - 代码里的 DEFAULT_NODE_PROFILES 是默认档；
  - Settings.llm_node_models / llm_node_thinking 可覆盖；
  - 未登记节点走全局默认模型，thinking=inherit（不显式传，跟 API 默认）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ThinkingMode = Literal["enabled", "disabled", "inherit"]

# 与 Settings.llm_model 缺省对齐；解析时仍以 Settings 为准
DEFAULT_MODEL = "deepseek-v4-pro"
FAST_MODEL = "deepseek-v4-flash"


@dataclass(frozen=True)
class NodeLLMProfile:
    node: str
    model: str                 # 解析后的模型 id（已折叠默认）
    thinking: ThinkingMode
    note: str = ""
    source: str = "default"    # default | env_model | env_thinking | env_both


# ── 默认档（只写「相对全局默认有差异」的节点）────────────────
# model=None → 用全局 STORY_LLM_MODEL；thinking 必须显式。
_DEFAULT_SPEC: dict[str, tuple[str | None, ThinkingMode, str]] = {
    # 高频轻节点：flash + 关推理
    "director_dispatch": (FAST_MODEL, "disabled", "最高频；只派流向/目标"),
    "character": (FAST_MODEL, "disabled", "最高频；schema 焊死实现段"),
    "continuity_critic": (FAST_MODEL, "disabled", "判是非+JSON，不必深想"),
    "faithfulness_check": (FAST_MODEL, "disabled", "蕴含判定，关推理"),
    "reconciler": (FAST_MODEL, "disabled", "对账动作选择，关推理"),
    "extractor": (FAST_MODEL, "disabled", "贵在输出长，不在推理"),
    "summarizer": (FAST_MODEL, "disabled", "蒸馏摘要，关推理"),
    # 规划/创世：仍走全局默认模型；thinking 暂 inherit（本轮不动）
    "planner": (None, "inherit", "章规划；本轮保持 API 默认"),
    "replanner": (None, "inherit", "卷复盘；漂移度量"),
    "director_setup": (None, "inherit", "拆场；本轮保持 API 默认"),
    "director_setup_redirect": (None, "inherit", "场重导；同 setup"),
    "architect": (None, "inherit", "创世/扩卷"),
    "worldbuilder": (None, "inherit", "世界圣经"),
    "writer": (None, "inherit", "散文渲染；可 skip"),
}

# 别名：调用时的 node 名 → 表内主名
_ALIASES: dict[str, str] = {
    "director_setup_redirect": "director_setup_redirect",
}


@dataclass(frozen=True)
class NodeProfileResolver:
    """把默认档 + env 覆盖折成最终 NodeLLMProfile。"""

    default_model: str = DEFAULT_MODEL
    model_overrides: dict[str, str] | None = None
    thinking_overrides: dict[str, ThinkingMode] | None = None

    def resolve(self, node: str) -> NodeLLMProfile:
        key = _ALIASES.get(node, node)
        spec = _DEFAULT_SPEC.get(key)
        base_model = (spec[0] if spec else None) or self.default_model
        base_thinking: ThinkingMode = spec[1] if spec else "inherit"
        note = spec[2] if spec else "未登记节点，走全局默认"
        model = base_model
        thinking = base_thinking
        src_model = False
        src_think = False
        if self.model_overrides and node in self.model_overrides:
            model = self.model_overrides[node]
            src_model = True
        elif self.model_overrides and key in self.model_overrides:
            model = self.model_overrides[key]
            src_model = True
        if self.thinking_overrides and node in self.thinking_overrides:
            thinking = self.thinking_overrides[node]
            src_think = True
        elif self.thinking_overrides and key in self.thinking_overrides:
            thinking = self.thinking_overrides[key]
            src_think = True
        if src_model and src_think:
            source = "env_both"
        elif src_model:
            source = "env_model"
        elif src_think:
            source = "env_thinking"
        else:
            source = "default"
        return NodeLLMProfile(
            node=node, model=model, thinking=thinking, note=note, source=source
        )

    def roster(self) -> list[NodeLLMProfile]:
        """全部已登记节点 + 覆盖里多出来的名字，稳定排序。"""
        names = set(_DEFAULT_SPEC)
        if self.model_overrides:
            names.update(self.model_overrides)
        if self.thinking_overrides:
            names.update(self.thinking_overrides)
        return [self.resolve(n) for n in sorted(names)]


def resolver_from_settings(settings=None) -> NodeProfileResolver:
    from story_engine.config import load_settings

    s = settings or load_settings()
    return NodeProfileResolver(
        default_model=s.llm_model,
        model_overrides=dict(s.llm_node_models or {}),
        thinking_overrides=dict(s.llm_node_thinking or {}),  # type: ignore[arg-type]
    )


def format_roster(profiles: list[NodeLLMProfile], *, as_json: bool = False) -> str:
    if as_json:
        import json

        return json.dumps(
            [
                {
                    "node": p.node,
                    "model": p.model,
                    "thinking": p.thinking,
                    "source": p.source,
                    "note": p.note,
                }
                for p in profiles
            ],
            ensure_ascii=False,
            indent=2,
        )
    cols = ("node", "model", "thinking", "source", "note")
    rows = [(p.node, p.model, p.thinking, p.source, p.note) for p in profiles]
    widths = [len(c) for c in cols]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    head = "  ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    sep = "  ".join("-" * widths[i] for i in range(len(cols)))
    body = ["  ".join(r[i].ljust(widths[i]) for i in range(len(cols))) for r in rows]
    return "\n".join([head, sep, *body])


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="查询节点 LLM 配置表")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--node", help="只查一个节点")
    args = parser.parse_args(argv)
    r = resolver_from_settings()
    if args.node:
        profiles = [r.resolve(args.node)]
    else:
        profiles = r.roster()
        print(f"# default_model = {r.default_model}")
        print("# 查单节点: uv run python -m story_engine.llm --node character")
        print()
    print(format_roster(profiles, as_json=args.json))


if __name__ == "__main__":
    main()
