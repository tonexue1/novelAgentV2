# Summarizer（摘要）

> **层**：recorder ｜ **类型**：LLM（低温/定种）｜ **触发**：章末
> **提示词**：待定（本文先略）

## 做什么

产 scene / chapter 级多分辨率摘要（蒸馏梗概 + 轻结构化 facet），供长程检索"越远越压缩"。摘要即语义检索的 embed 对象。（volume/saga 级摘要由 [replanner](../planning/replanner.md) 卷/篇末产。）

## 入参

- [script-store](../../schema/stores/script-store.md) ChapterScript（scene/chapter 覆盖范围）。

## 输出

- [summary-store](../../schema/stores/summary-store.md) SummaryEntry（level=scene|chapter，text + covers + threads/cast/key_ops）→ 独立 SummaryDelta。
- `vec` 建在 text 上（交 [embedder](../system/embedder.md)）。

## 交互

- **上游**：过闸 ChapterScript。
- **下游**：[applier](../system/applier.md) 写 summary-store。

## 要害

`covers` 逐层收敛（scene 级才回指原文 beat）；带 `summarizer_version` 版本化，(level,ref) 幂等替换；保真度守 D。
