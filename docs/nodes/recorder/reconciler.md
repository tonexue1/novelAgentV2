# Reconciler（对账）

> **层**：recorder ｜ **类型**：LLM ｜ **触发**：章末（faithfulness-check 之后）
> **提示词**：待定（本文先略）

## 做什么

把过校验的候选与相关旧记忆对账，决定**写回动作**：ADD / REINFORCE / SOFT-INVALIDATE / NOOP（替代 mem0 的 DELETE）；伏笔/主线走状态机 op（PLANT/REINFORCE/FULFILL/ABANDON/ADVANCE/…）。矛盾走软失效不删。

## 入参

- 过 [faithfulness-check](../validation/faithfulness-check.md) 的候选。
- 相关旧记忆 → [memory-store](../../schema/stores/memory-store.md)；旧台账 → [arc-store](../../schema/stores/arc-store.md)。

## 输出

- [recorder-output](../../schema/artifacts/recorder-output.md)：定了 action/target_id 的 `mem_ops` + `arc_ops` + `world_ops` + `tier_noms`（原子批）。

## 交互

- **上游**：[extractor](./extractor.md) → [faithfulness-check](../validation/faithfulness-check.md)。
- **下游**：[applier](../system/applier.md) 确定性落库。

## 要害

REINFORCE/SOFT-INVALIDATE 须先检索旧条目拿 target_id；NOOP 留档供审计/幂等；去重按 `(scope,type,归一化text)`。
