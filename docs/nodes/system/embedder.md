# Embedder（向量化）

> **层**：system ｜ **类型**：系统（模型服务，非推理）｜ **触发**：写摘要/记忆时
> **提示词**：无

## 做什么

文本 → 向量。为记忆条目、摘要（embed 对象=摘要 text）产 embedding，供语义检索。

## 入参

- 待向量化文本（[memory-store](../../schema/stores/memory-store.md) `text`、[summary-store](../../schema/stores/summary-store.md) `text`、voice 例句等）。

## 输出

- `vec` embedding，回写对应条目。

## 交互

- **被调**：[applier](./applier.md)（落库时）、[summarizer](../recorder/summarizer.md)、[retriever](./retriever.md)（query 向量）。

## 要害

模型选型待定（见技术选型待办）；摘要级向量低噪、数量少。
