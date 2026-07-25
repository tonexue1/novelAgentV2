# Faithfulness Check（忠实性校验）

> **层**：validation ｜ **类型**：系统 + LLM ｜ **触发**：抽取后（Extractor → Reconciler 之间）
> **提示词**：待定（蕴含判定部分）

## 做什么

守 U（记忆是否忠于剧本）：反幻觉硬底线。**精度为硬底线 + 召回尽力**。每个候选 op 必须被其 evidence 蕴含才放行；撑不起 = 拒。抽取幻觉是漂移源头之一，D 把它挡在 U 步。

## 入参

- [extractor](../recorder/extractor.md) 的候选 ops（含 evidence）。
- 对照原文 → [script-store](../../schema/stores/script-store.md)（evidence 指向的 scene/beat）。

## 输出

- 过校验的候选（交 [reconciler](../recorder/reconciler.md)）；拒的记抽取错误日志。

## 两关

1. **跨度存在**（系统硬检）：evidence 解析到已提交 ScriptStore 位置，否则硬拒。
2. **蕴含判定**（LLM）：evidence 文本是否支撑该 op。

## 交互

- **上游**：[extractor](../recorder/extractor.md)。
- **下游**：[reconciler](../recorder/reconciler.md)。

## 要害

镜像 continuity-critic（B 守 f / D 守 U，夹住递推两项）。召回漏掉靠"Script 永在、以后可重抽"兜底。
