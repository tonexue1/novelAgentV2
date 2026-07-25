# Orchestrator（编排）

> **层**：system ｜ **类型**：系统 ｜ **触发**：全程
> **提示词**：无

## 做什么

编排三相循环（初始化 / 每章 / 卷边界）：调度各节点、管重试与并发、维护运行态工作缓冲、铸 volume/chapter id、章末清空缓冲。**初始化相**跑创世子流程（G0~G5，见 ARCHITECTURE §2.6）造出冷启动 S₀。

## 入参

- 各节点的就绪信号 / 闸门结果 / 循环状态。

## 输出

- 节点调用序列；工作缓冲（本章已生成、未落库的场景/beat，供 assembler 顺序带）。
- 铸 `v{k}` / `c{n}` 位置 id（递增）。

## 交互

- **驱动**：全体节点。
- **配合**：[consistency-gate](./consistency-gate.md)（重试/升级）、[assembler](./assembler.md)（工作缓冲）。

## 要害

顺序递推不跳章（BLOCK 挂起等人）；场景运行循环 = setup → (dispatch⇄character)* → 收场 → Critic。
