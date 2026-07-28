"""prompt 拼装小工具（M2 糙版）。

节点各自写自己的模板；这里只提供公共的序列化 / 分节，避免每个节点重复。
LLM 节点之间只传结构化 artifact，所以 prompt 里注入的上下文一律是 JSON。
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel


def as_json(obj: Any, *, limit: int | None = None) -> str:
    """pydantic 模型 / 普通对象 → 紧凑 JSON（去 None，保中文）。"""
    if isinstance(obj, BaseModel):
        data: Any = obj.model_dump(mode="json", exclude_none=True)
    elif isinstance(obj, (list, tuple)):
        data = [
            o.model_dump(mode="json", exclude_none=True) if isinstance(o, BaseModel) else o
            for o in obj
        ]
    else:
        data = obj
    text = json.dumps(data, ensure_ascii=False)
    if limit is not None and len(text) > limit:
        text = text[:limit] + "…(截断)"
    return text


def section(title: str, body: str) -> str:
    return f"## {title}\n{body}"


def build_prompt(role: str, task: str, sections: Iterable[tuple[str, str]]) -> str:
    """role（你是谁）+ task（干什么）+ 若干上下文分节。

    结构化输出的 JSON Schema 仍由 instructor 注入；
    **合法取值说明**由各 schema.llm_vocab() 以分节形式挂进 sections，禁止节点手抄枚举。
    """
    parts = [f"# 角色\n{role}", f"# 任务\n{task}"]
    parts.extend(section(t, b) for t, b in sections if b)
    return "\n\n".join(parts)
