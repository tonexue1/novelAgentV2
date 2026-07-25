# Hard-Check（确定性硬检）

> **层**：validation ｜ **类型**：系统 ｜ **触发**：每个生成节点后 / 每拍（近零成本）
> **提示词**：无（确定性规则）

## 做什么

在制造错误的那一棒当场拦可判定项。规则如：角色在世/在场、地点存在于 WorldStore、能力 ≤ 当前等级(as-of)、引用的 thread_id/fs_id 存在、伏笔 FULFILL 前必有 PLANT、POV 角色在场、境界 ladder 单调、地理防瞬移。

## 入参

- 待检 artifact（L3 / SceneScript / Beat）。
- 对照真相：[world-store](../../schema/stores/world-store.md)（loc/ladder/relations）、[arc-store](../../schema/stores/arc-store.md)（fs/thread 状态）、[memory-store](../../schema/stores/memory-store.md)（ability as-of）、[script-store](../../schema/stores/script-store.md)（在场/POV）。

## 输出

- 通过 / [violation-log](../../schema/stores/violation-log.md) Violation（check_type=hard，多为 BLOCK）。

## 交互

- 嵌在 [consistency-gate](../system/consistency-gate.md) 内，每个生成节点（planner/setup/dispatch/character）后即时跑。

## 要害

守 f 的结构性底线；可判定即拦，不判语义（语义交 continuity-critic）。
