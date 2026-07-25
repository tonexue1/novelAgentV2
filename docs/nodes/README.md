# Nodes（数据处理节点）

数据流上每个处理节点（LLM / 系统 / 复合 flow）的 **做什么 / 入参 / 输出 / 交互**。字段级 schema 见 [`../schema/`](../schema/README.md)。`ARCHITECTURE.md §4` 仅留索引。

> **LLM 提示词**：本目录暂略（先定 I/O 契约与编排，prompt 后续单独设计）。

## 六层

| 层 | 触发 | 节点 |
|----|------|------|
| **planning/** | 初始化 / 卷边界 | [architect](./planning/architect.md) · [worldbuilder](./planning/worldbuilder.md) · [replanner](./planning/replanner.md) · [planner](./planning/planner.md) |
| **production/** | 每章循环 | [director-setup](./production/director-setup.md) · [director-dispatch](./production/director-dispatch.md) · [character](./production/character.md) |
| **recorder/** | 章末（过闸后） | [extractor](./recorder/extractor.md) · [reconciler](./recorder/reconciler.md) · [summarizer](./recorder/summarizer.md) |
| **validation/** | 生成后 / 抽取后 | [hard-check](./validation/hard-check.md) · [continuity-critic](./validation/continuity-critic.md) · [faithfulness-check](./validation/faithfulness-check.md) |
| **system/** | 编排驱动 | [retriever](./system/retriever.md) · [assembler](./system/assembler.md) · [embedder](./system/embedder.md) · [chunker](./system/chunker.md) · [applier](./system/applier.md) · [consistency-gate](./system/consistency-gate.md) · [orchestrator](./system/orchestrator.md) |
| **consumption/** | 按需渲染 | [writer](./consumption/writer.md) · [vlm](./consumption/vlm.md) |

## 类型图例

- **LLM**：一次（或少数几次）语言模型调用，产结构化 artifact。
- **系统**：确定性变换/检索/落库/编排，零或近零 LLM。
- **复合 flow**：内部多步（LLM+系统）子流水，本文只定外层契约。

## 数据流（三相，节点视角）

```
① 初始化:  种子 → architect ⇄ worldbuilder → plan-store(L0/L1) ─[人工关卡]─▶ L2[卷1]

② 每章循环:
   planner ─L3▶[hard-check]─▶ director-setup ─SceneScript▶[hard-check]
      ▲(assembler←retriever 装上下文)          │
      │        ┌─── 逐场：现场调度循环 ───┐
      │        │ director-dispatch ─派工▶ character ─beat+handoff▶[hard-check]
      │        │        ▲___ 读实录/handoff ___│
      │        └── 承重拍全命中&退出 → 收场 ──┘ 每场
      │              [consistency-gate: hard-check + continuity-critic] ──未过──▶ violation-log → 升级阶梯
      │                       │ 过闸
      │              recorder: extractor →[faithfulness-check]→ reconciler + summarizer
      │              applier ─▶ script/memory/arc/summary/world stores
      └──────────────────────┘ 下一章（缓冲清空）

③ 卷边界:  replanner 读 实际(arc/memory) vs 意图(L1) → 更新 L1/L2/volume摘要/loose-ends
```

## LLM↔系统交替原则

LLM 节点之间不传自由文本，只传结构化 artifact（见 schema）；由系统节点（硬检/校验/装配/落库/编排）在中间**校验后流转**。
