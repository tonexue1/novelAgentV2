"""存储层：抽象协议 + 后端实现。"""

from story_engine.stores.base import Store
from story_engine.stores.json_backend import JsonStore

__all__ = ["Store", "JsonStore"]
