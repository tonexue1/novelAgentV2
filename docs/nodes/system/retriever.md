# Retriever（检索）

> **层**：system ｜ **类型**：系统 ｜ **触发**：装配上下文时（被 assembler 调）
> **提示词**：无

## 做什么

分桶检索，不做一次 top-k 打天下：按 scope/type/章节窗**过滤**，再向量排序，再 as-of 裁剪。三桶分离：轨迹桶 / 人设桶（画像+经历子桶）/ 流水桶。filter-then-rank + as-of 查询。

## 入参

- query（节点意图 / 本拍上下文）+ 过滤条件（scope/type/章节窗/facet）。
- [memory-store](../../schema/stores/memory-store.md) / [arc-store](../../schema/stores/arc-store.md) / [summary-store](../../schema/stores/summary-store.md) / [world-store](../../schema/stores/world-store.md)。

## 输出

- 候选条目集（各桶），交 [assembler](./assembler.md) 按预算取舍。

## 交互

- **被调**：[assembler](./assembler.md)。
- **用**：[embedder](./embedder.md) 的向量。

## 要害

多分辨率长程：近段命中原文、远段命中章/卷摘要；证据锚定回调走 evidence 指针（skip-connection）。
