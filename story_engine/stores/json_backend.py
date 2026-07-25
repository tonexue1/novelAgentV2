"""JSON/JSONL 后端 —— M0 的零依赖 Store 实现。

- append-only 落 JSONL（每行一条），可 diff、易调试。
- as_of：内存过滤 t_valid / t_invalid（字段可选，缺省视为始终可见）。
- 主键字段可配（默认取模型第一个字段）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class JsonStore(Generic[T]):
    def __init__(
        self,
        model: type[T],
        path: str | Path,
        key_field: str | None = None,
    ) -> None:
        self._model = model
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # 主键字段：显式指定，否则取模型第一个字段
        self._key_field = key_field or next(iter(model.model_fields))
        self._items: list[T] = []
        self._load()

    # ── 持久化 ────────────────────────────────────────────────
    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    self._items.append(self._model.model_validate_json(line))

    def _append_line(self, entry: T) -> None:
        with self._path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    # ── Store 协议 ────────────────────────────────────────────
    def append(self, entry: T) -> str:
        self._items.append(entry)
        self._append_line(entry)
        return str(getattr(entry, self._key_field))

    def get(self, key: str) -> T | None:
        for it in self._items:
            if str(getattr(it, self._key_field)) == key:
                return it
        return None

    def all(self) -> list[T]:
        return list(self._items)

    def query(self, **filters: object) -> list[T]:
        return [it for it in self._items if self._match(it, filters)]

    def as_of(self, chapter: int, **filters: object) -> list[T]:
        out: list[T] = []
        for it in self._items:
            if not self._match(it, filters):
                continue
            t_valid = getattr(it, "t_valid", None)
            if t_valid is not None and t_valid > chapter:
                continue  # 尚未生效（未来泄漏）
            t_invalid = getattr(it, "t_invalid", None)
            if t_invalid is not None and t_invalid <= chapter:
                continue  # 已软失效
            out.append(it)
        return out

    @staticmethod
    def _match(item: BaseModel, filters: dict[str, object]) -> bool:
        return all(getattr(item, k, None) == v for k, v in filters.items())

    def __len__(self) -> int:
        return len(self._items)
