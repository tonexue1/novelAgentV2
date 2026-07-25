# Worldbuilder（世界设计师）

> **层**：planning ｜ **类型**：LLM ｜ **触发**：创世 + 按需（晋升补定义）
> **提示词**：待定（本文先略）

## 做什么

生成并维护 WorldStore 的**承重 canon**（core/major）：概念/功法/地理/势力/物件/种族的权威 `definition` 与结构化 `attributes`（如境界 ladder）。奉行"小核心"——只种少量承重设定，海量长尾留给生产层现场造。

## 入参

- 人工种子 / L0（创世时）→ [plan-store](../../schema/stores/plan-store.md)。
- 待补实体清单（Replanner 晋升 minor→major/core 时指定）。

## 输出

- [world-store](../../schema/stores/world-store.md)：`WorldEntity`（tier=core/major，origin=seeded），权威 definition + attributes + relations。
- 铸 `concept./art./loc./org./item./race.` id（→ [ids](../../schema/primitives/ids.md)）。

## 交互

- **创世**：与 [architect](./architect.md) 协同循环（种子→L0→造 canon ⇄ 写 L1 互引 →L2）。
- **按需**：[replanner](./replanner.md) 确认晋升 → 唤本节点补权威 definition。
- **长尾对照**：minor 由 [director-setup](../production/director-setup.md)/[character](../production/character.md) 现场造、[recorder](../recorder/extractor.md) 登记。

## 要害

权威 `definition` 唯一，下游 LLM 只读不重编（防概念漂移第一支柱）。
