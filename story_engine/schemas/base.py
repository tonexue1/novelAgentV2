"""schema 公共基类。

对应 docs/schema/ 的 pydantic 落地。字段以 docs/schema/ 为权威；
跑出来若与文档冲突，回改文档并记版本（见 ROADMAP「schema 是当前最佳假设」）。
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
