# Writer（写作器）

> **层**：consumption ｜ **类型**：复合 flow（LLM+系统）｜ **触发**：按需渲染
> **提示词**：待定（本文先略）
> **状态**：内部多步 flow 待专门设计，**当前只定外层契约、不冻结**。

## 做什么

把媒介无关的 Script 渲染成散文成品，写入 ManuscriptStore。可重渲染、可多版本。

## 入参（外层契约）

- [script-store](../../schema/stores/script-store.md) Script + voice/文风（[memory-store](../../schema/stores/memory-store.md) voice）+ 前文。
- [world-store](../../schema/stores/world-store.md) 渲染保真所需 canon。

## 输出

- 散文 → ManuscriptStore（成品层，未冻结）。

## 内部 flow（待展开）

≥ 检索文风/前文 → 逐场渲染 → 风格一致性校验 → 成稿。

## 要害

只消费 Script，不反写真相层；渲染指令不污染剧本。
