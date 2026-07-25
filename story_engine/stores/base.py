"""Store 抽象层。

统一读写契约：append（只追加）/ get / query / as_of。
- ScriptStore 语义：只追加、永不改。
- 派生 store 语义：追加 + 软失效（写 t_invalid，不物理删）。
后端可换（M0 = JSON）。as-of 主时钟 = chapter（int）。
"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@runtime_checkable
class Store(Protocol[T]):
    def append(self, entry: T) -> str:
        """追加一条，返回其主键。"""
        ...

    def get(self, key: str) -> T | None:
        ...

    def all(self) -> list[T]:
        ...

    def query(self, **filters: object) -> list[T]:
        """按字段等值过滤。"""
        ...

    def as_of(self, chapter: int, **filters: object) -> list[T]:
        """as-of 章过滤：只返回该章可见（t_valid<=chapter 且未软失效）的条目。"""
        ...
