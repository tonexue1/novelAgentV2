# Consistency Gate（一致性闸）

> **层**：system ｜ **类型**：系统（编排 hard-check + critic）｜ **触发**：每生成节点 / 每场
> **提示词**：无

## 做什么

真相层守门人：驱动 hard-check + Continuity Critic，按严重度走**重试 / 升级阶梯 / 放行**。没过闸的内容不许进 ScriptStore。铸 violation id。

## 入参

- 待检产物 + [hard-check](../validation/hard-check.md) / [continuity-critic](../validation/continuity-critic.md) 结果。

## 输出

- 过闸信号（clean/flagged）/ 挂起(blocked)；[violation-log](../../schema/stores/violation-log.md) 记录 + 生命周期更新。

## 升级阶梯与降级

```
beat 补丁 → 场景重导(setup) → 整章重规划(planner) → 卷复盘(replanner)
```
- 默认每级重试 N=2；**CORRECT** 耗尽→接受最优候选 + `flagged` 放行；**BLOCK** 爬满→挂起该章 + 呼人；**ADVISORY** 只记。
- **M3 已接**：逐拍硬检 + 场收束（硬检 + Continuity Critic）+ 阶梯前三级（retry / redirect / replan_chapter）+ 挂起。
- **阶梯第四级（Replanner 卷复盘）仍属 M4**——爬满后挂起呼人，不自动卷复盘。

## 交互

- **驱动**：[hard-check](../validation/hard-check.md)、[continuity-critic](../validation/continuity-critic.md)。
- **升级到**：[director-setup](../production/director-setup.md) / [planner](../planning/planner.md) / [replanner](../planning/replanner.md)（M4）。
- **过闸后**：[applier](./applier.md) + [recorder](../recorder/extractor.md)。编排见 `story_engine/orchestrator/loop.py`。

## 要害

BLOCK 永不静默入库；所有闸门结果与重试留痕（可观测 + 供卷复盘）。
