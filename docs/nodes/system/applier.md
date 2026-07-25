# Applier（落库）

> **层**：system ｜ **类型**：系统 ｜ **触发**：过闸后 / 章末 / 卷末
> **提示词**：无

## 做什么

确定性落库（原写作/落库职责统一为此；Writer 只指写作器）。append Script 流水、铸 beat id 定序、应用 RecorderOutput（mem/arc/world/tier）、更新伏笔/主线 status、写摘要索引。ArcUpdater 的确定性写归入此；模糊判断上移 Reconciler。

## 入参

- 过闸 Script beats（[script-store](../../schema/stores/script-store.md)）。
- [recorder-output](../../schema/artifacts/recorder-output.md)（原子批）。
- SummaryDelta（[summary-store](../../schema/stores/summary-store.md)）。

## 输出

- 写入各 store：script / memory / arc / world（演化） / summary。
- 铸 `beat` id、`m.{ulid}` memory id。

## 交互

- **上游**：[consistency-gate](./consistency-gate.md)（过闸）、[reconciler](../recorder/reconciler.md)、[summarizer](../recorder/summarizer.md)。
- **调**：[embedder](./embedder.md)、[chunker](./chunker.md)。

## 要害

只做确定性写；一章一次原子 apply；NOOP 只记日志不碰库。
