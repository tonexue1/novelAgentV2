# Replanner（卷复盘师）

> **层**：planning ｜ **类型**：LLM ｜ **触发**：卷 / 篇边界
> **提示词**：待定（本文先略）

## 做什么

卷边界复盘：先**诊断漂移**（实际 vs 意图），再**带约束修正**。默认只改下一卷 L2 把剧情拽回；仅当 L1 里程碑不可达 / 出现更优涌现才提 L1 结构性修订(v+1)。同时产 volume/saga 摘要、loose-ends 报告，确认 emergent 伏笔与人物 tier 晋升。

## 入参

- 意图：[plan-store](../../schema/stores/plan-store.md) L1。
- 实际：[arc-store](../../schema/stores/arc-store.md)（thread/fs 进度）、[memory-store](../../schema/stores/memory-store.md)（goal/trait 轨迹）。
- [violation-log](../../schema/stores/violation-log.md)：反复失败的 category/refs 聚合（漂移信号）。
- 待确认：Recorder 的 emergent 伏笔提名、`tier_noms`（→ [recorder-output](../../schema/artifacts/recorder-output.md)）。

## 输出

- L1 进度更新 / 结构性修订(v+1，走人工关卡)、L2[下一卷]（sketch→detailed 滚出）。
- volume / saga 摘要 → [summary-store](../../schema/stores/summary-store.md)。
- loose-ends 报告；确认 emergent 入账 + 唤 [worldbuilder](./worldbuilder.md) 补定义 + 人物 tier 晋升。

## 交互

- **上游**：一致性闸升级阶梯第④级 / 卷边界定时触发。
- **下游**：[planner](./planner.md) 消费更新后的 L1/L2。

## 要害

是宏观误差投影（接微观闸门顶端）。core 伏笔逾期 = BLOCK 呼人，不许自动漂/废。
