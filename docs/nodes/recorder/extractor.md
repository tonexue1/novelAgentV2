# Extractor（抽取）

> **层**：recorder ｜ **类型**：LLM（低温/定种）｜ **触发**：章末（过闸后）
> **提示词**：待定（本文先略）

## 做什么

从过闸 ChapterScript 尽力抽取记忆/伏笔/世界/分级候选（召回优先）。每条候选**必带 evidence** 回指 Script 位置。结构化变换非创作，用 temp=0 压低非确定性。

## 入参

- 过闸 [script-store](../../schema/stores/script-store.md) ChapterScript（全文）。
- 相关旧记忆（供对账参考）→ [memory-store](../../schema/stores/memory-store.md)。

## 输出（候选，待校验+对账）

- mem 候选：fact/belief/trait/voice/ability/goal + involves/salience。
- arc 候选：伏笔/主线 ops + secret（含 knowledge/known_by）。
- world 候选：minor 登记 + state 演化。
- tier 提名。
- 汇成 [recorder-output](../../schema/artifacts/recorder-output.md) 的候选态。

## 交互

- **上游**：[consistency-gate](../system/consistency-gate.md) 过闸信号。
- **下游**：[faithfulness-check](../validation/faithfulness-check.md)（证据蕴含）→ [reconciler](./reconciler.md)。

## 要害

召回尽力、精度交给下游 faithfulness-check 把关；evidence 跨度不存在 = 直接被拒。
