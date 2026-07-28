"""schema 公共基类。

对应 docs/schema/ 的 pydantic 落地。字段以 docs/schema/ 为权威；
跑出来若与文档冲突，回改文档并记版本（见 ROADMAP「schema 是当前最佳假设」）。

LLM 约定：凡进 complete_structured 的响应模型及其入参上下文 schema，
须提供 llm_vocab()（取值说明）；节点 prompt 引用之，禁止手抄第三份枚举。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaModel(BaseModel):
    """所有 store/artifact 模型的基类。"""

    model_config = ConfigDict(
        extra="forbid",       # 未知字段直接报错，早暴露漂移
        validate_assignment=True,
        frozen=False,
    )

    @classmethod
    def llm_vocab(cls) -> str:
        """给模型看的取值/形状说明。LLM 面向 schema 必须覆盖；默认空串。"""
        return ""


class Temporal:
    """as-of 时间语义 mixin（显式化，替代 Store 里的鸭子类型探字段）。

    带此 mixin 的条目须有 t_valid（生效章）与 t_invalid（软失效章，None=仍有效）。
    Store.as_of 用 isinstance(item, Temporal) 判定，无此 mixin 者视为始终可见。
    """

    t_valid: int
    t_invalid: int | None

    def visible_as_of(self, chapter: int) -> bool:
        if self.t_valid > chapter:
            return False  # 尚未生效（未来泄漏）
        if self.t_invalid is not None and self.t_invalid <= chapter:
            return False  # 已软失效
        return True
