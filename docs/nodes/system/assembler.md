# Assembler（上下文装配）

> **层**：system ｜ **类型**：系统 ｜ **触发**：每次 LLM 节点调用前
> **提示词**：无

## 做什么

按**节点画像**（各节点读什么/分辨率/要害）+ token 预算，把 Retriever 的候选装配成该节点的上下文。分级 MUST/SHOULD/MAY 择优；lean-by-default，widen-on-error。按 token 记账自动偏向"多塞蒸馏、少塞原文"。

## 入参

- 目标节点标识 + 其上下文画像（Planner 粗 / setup 中 / dispatch 轻 / Character 细 / Critic 宽）。
- [retriever](./retriever.md) 候选 + 工作缓冲（本章已生成、未落库，编排内存）。

## 输出

- 装配好的上下文（喂对应 LLM 节点）。

## 交互

- **调**：[retriever](./retriever.md)。
- **服务对象**：planner / director-setup / director-dispatch / character / continuity-critic / extractor。

## 要害

认知边界：给 Character 装配时按 POV 过滤（人设桶经历 + 工作缓冲）；预算不够先砍 MAY 再砍 SHOULD，MUST 不动。
