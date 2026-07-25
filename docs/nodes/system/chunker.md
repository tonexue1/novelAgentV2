# Chunker（切分）

> **层**：system ｜ **类型**：系统 ｜ **触发**：落库 / 检索预处理
> **提示词**：无

## 做什么

章 → 场景块切分，为检索/embedding 提供合适粒度的单元。对齐位置 id（scene/beat）。

## 入参

- [script-store](../../schema/stores/script-store.md) ChapterScript。

## 输出

- 场景块（对齐 `c{n}.s{m}` / beat 跨度），供 embedder/retriever 使用。

## 交互

- **上游**：[applier](./applier.md) 落库流程。
- **下游**：[embedder](./embedder.md) / [retriever](./retriever.md)。

## 要害

切分边界须与 EvidenceSpan 可解析对齐（守 U 的寻址前提）。
