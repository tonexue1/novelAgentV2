"""Node 协议 + 上下文。

节点分两类（见 docs/nodes/README.md）：
  - LLM 节点：通过 LLMClient 产结构化 artifact；
  - 系统节点：确定性读写 store / 校验 / 路由。
M0 只定协议 + 关键 stub，真实逻辑留到 M1+。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from story_engine.llm.base import LLMClient
from story_engine.telemetry.runrecord import Telemetry


@dataclass
class NodeContext:
    """节点运行上下文：注入 LLM 客户端、留痕、当前章。"""

    llm: LLMClient | None = None
    telemetry: Telemetry | None = None
    chapter: int | None = None
    stores: dict[str, object] = field(default_factory=dict)


class Node(Protocol):
    name: str

    def run(self, ctx: NodeContext, **inputs: object) -> object:
        ...
