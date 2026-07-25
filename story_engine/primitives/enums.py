"""共享枚举 —— 对应 docs/schema/primitives/common.md 的「共享枚举」。

集中定义一处，避免各 schema 散抄漂移。
"""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    """违规严重度 → violation-log。"""

    BLOCK = "BLOCK"
    CORRECT = "CORRECT"
    ADVISORY = "ADVISORY"


class Importance(str, Enum):
    """伏笔 / 世界实体重要度。"""

    CORE = "core"
    MAJOR = "major"
    MINOR = "minor"


class WorldTier(str, Enum):
    """世界实体分层 → world-store。"""

    CORE = "core"
    MAJOR = "major"
    MINOR = "minor"


class CharTier(int, Enum):
    """角色分层 → memory-store（画像完整度 / 检索降权）。"""

    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3


class DetailLevel(str, Enum):
    """规划详细度 → plan-store 滚动地平线。"""

    SKETCH = "sketch"
    DETAILED = "detailed"


class Resolution(str, Enum):
    """记忆软失效原因。"""

    ACHIEVED = "achieved"
    ABANDONED = "abandoned"
    SUPERSEDED = "superseded"
