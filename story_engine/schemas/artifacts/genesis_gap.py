"""GenesisGap：Genesis Gate 诊断产物 —— 对应 ARCHITECTURE §2.6。

Gate 未过 / 迭代超上界时的载体：喂回 G2 自动补，或 ESCALATE 交人工 G3。
（本 schema 为 M0 落地，尚未在 docs/schema/ 独立成文，跑通后回填。）
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from story_engine.schemas.base import SchemaModel


class GenesisVerdict(str, Enum):
    PASS = "PASS"            # 收敛，进 G3/G4
    REITERATE = "REITERATE"  # 未闭合，回 G2 再补（未超上界 N）
    ESCALATE = "ESCALATE"    # 超上界或死锁，交人工 G3


class GenesisGap(SchemaModel):
    verdict: GenesisVerdict
    iteration: int = 0
    dangling: list[str] = Field(default_factory=list)      # L1 要但 WorldStore 没建
    missing_def: list[str] = Field(default_factory=list)   # 存在但 core/major 缺权威 definition
    uncovered: list[str] = Field(default_factory=list)     # L0 意图未被任何 main thread 支撑
    open_questions: list[str] = Field(default_factory=list)  # 软复核提的待决问题（给人工）
    notes: str | None = None                               # 人工驳回回填，带回 G2

    @property
    def closure_ok(self) -> bool:
        return not self.dangling and not self.missing_def

    @property
    def coverage_ok(self) -> bool:
        return not self.uncovered
