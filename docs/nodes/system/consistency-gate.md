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
- **M4b 第四级**：`replan_budget` 耗尽且仍有 BLOCK → 动作 `escalate_volume`（不入库本章，编排层调 Replanner 卷复盘）；core 伏笔逾期可直接 `escalate_volume`。

## 卷边界编排

- walk / orchestrator 在卷末章（L2 `chapter_beats` 最大 `planned_seq`，或 `Volume.chapter_range` 末）调用 `run_volume_review` → Replanner。
- Gate `escalate_volume` 与卷末定时共用同一入口。

## 交互

- **驱动**：[hard-check](../validation/hard-check.md)、[continuity-critic](../validation/continuity-critic.md)。
- **升级到**：[director-setup](../production/director-setup.md) / [planner](../planning/planner.md) / [replanner](../planning/replanner.md)。
- **过闸后**：[applier](./applier.md) + [recorder](../recorder/extractor.md)。编排见 `story_engine/orchestrator/loop.py`。

## 要害

BLOCK 永不静默入库；所有闸门结果与重试留痕（可观测 + 供卷复盘）。
