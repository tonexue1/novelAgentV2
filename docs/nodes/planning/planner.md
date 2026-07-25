# Planner（章规划）

> **层**：planning ｜ **类型**：LLM ｜ **触发**：每章开头
> **提示词**：待定（本文先略）

## 做什么

把 L2 粗章槽落成**本章可执行方向**（ChapterPlan=L3），喂 Director·setup 拆场，并留追溯链给漂移度量。只到章级义务，不映射到场。强提示优先收临期/逾期伏笔。

## 入参

- [plan-store](../../schema/stores/plan-store.md) L0/L1/L2 + L2 派生的 foreshadow due list。
- [arc-store](../../schema/stores/arc-store.md)：thread 进度、到期/临期伏笔。
- 最近章摘要（粗）→ [summary-store](../../schema/stores/summary-store.md)。
- 上下文由 [assembler](../system/assembler.md)←[retriever](../system/retriever.md) 按**粗分辨率**装配。

## 输出

- [chapter-plan](../../schema/artifacts/chapter-plan.md)（L3）：chapter_goal / thread_advances / foreshadow_ops / cast(required) / story_beats / constraints / derived_from。

## 交互

- **上游**：[replanner](./replanner.md) 更新的 L1/L2。
- **下游**：[hard-check](../validation/hard-check.md) → [director-setup](../production/director-setup.md)。
- **检点**：查 PlanStore/ArcStore（死人出场、乱序推进、无视到期伏笔）。

## 要害

情节层决策，不要 beat 细节。casting 只到 tier 0/1/2；龙套走 `background_hint` 下放 Director。
