# Architect（总纲师，创世）

> **层**：planning ｜ **类型**：LLM ｜ **触发**：初始化一次
> **提示词**：待定（本文先略）

## 做什么

从人工种子（logline/设定）纯自上而下创世，产全局意图锚 P 的顶三层，并铸造 `th./fs./char.` 三类实体 id。L1 是全书防漂移主锚。与 Worldbuilder 协同循环（互相引用 world id 与主线）。

## 入参

- 人工种子：logline / 题材 / 母题 / 基调 / 结局方向 / 主角弧线意图。
- Worldbuilder 产出的 core/major canon（协同循环中互引）→ [world-store](../../schema/stores/world-store.md)。

## 输出

- [plan-store](../../schema/stores/plan-store.md)：**L0**（独占创立并冻结）+ **L1(v1)** + **L2[卷1]**。
- 铸 `th.{slug}` / `fs.{slug}` / `char.{slug}` id（→ [ids](../../schema/primitives/ids.md)）。

## 交互

- **上游**：人工种子 ⇄ [worldbuilder](./worldbuilder.md)（协同循环）。
- **下游**：[人工 review 关卡] → [planner](./planner.md) 逐章消费 L2/L1。
- **后续修订**：L1 结构性修订交 [replanner](./replanner.md)（创世只此一次）。

## 要害

L0 一旦冻结，改 = 换书。L1 是"意图 vs 实际"漂移度量的意图基准。
