# RecorderOutput / MemoryDelta / MemOp

> **权威源**：本文件。ARCHITECTURE §11.6 留索引指针。
> **类型**：Artifact（节点间消息）

## 摘要

Recorder 一章一趟同时吐记忆/伏笔/世界/分级四类增量，**打成一个原子批** `RecorderOutput` 交 Applier。管线：`Extractor`（尽力抓候选）→ `Faithfulness Check`（证据蕴含，反幻觉硬拒）→ `Reconciler`（对账定写回动作）→ `Applier`（确定性落库）。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | — | — | 无；每章一份 |
| 产出 | Recorder（Extractor+Faithfulness+Reconciler） | 章末 | 读过闸 ChapterScript |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Applier | 全批（原子 apply） | 落库到各 store |
| Replanner | tier_noms | 卷末确认人物分级 |

写入落点：`mem_ops`→[memory-store](../stores/memory-store.md)；`arc_ops`→[arc-store](../stores/arc-store.md)；`world_ops`→[world-store](../stores/world-store.md)（演化域）；`tier_noms`→memory-store（tier）。

## 字段

```
RecorderOutput:                            # Recorder→Applier，一章一次原子 apply
  chapter       : c{n}
  mem_ops       : MemOp[]                   # 本文件
  arc_ops       : ArcOp[]                    # 伏笔/主线/secret 状态机（→ arc-store）
  world_ops     : WorldOp[]                  # world minor 登记 + state as-of 演化（→ world-store）
  tier_noms     : { char: char.{slug}, from: int, to: int, reason: str, evidence: EvidenceSpan[] }[]
                                            # 人物分级提名（Replanner 卷复盘确认）
  extractor_version : str

MemOp:                                     # 对齐 memory-store 字段
  action        : ADD | REINFORCE | SOFT-INVALIDATE | NOOP
  target_id     : memory_entry_id?          # REINFORCE/SOFT-INVALIDATE 【必填】，指既有条目 m.{ulid}
  # —— 条目载荷（ADD 必填）——
  type          : fact | belief | trait | voice | ability | goal
  scope         : char.{slug} | th.{slug} | global
  text          : str
  t_valid       : c{n}                      # = 本章（as-of 主时钟）
  strength?     : float
  evidence      : EvidenceSpan[]            # 【必填】守 U，跨度不存在=系统硬拒
  involves?     : entity_id[]               # fact 用（关系触发检索前提）
  salience?     : float                     # fact 用（抗 recency 淹没）
  goal_kind?    : long-drive | stage-goal   # goal 专属
  parent?       : memory_entry_id           # goal 层级链
  example?      : str                       # voice 专属：真实台词例句（few-shot 库）
  resolution?   : achieved | abandoned | superseded   # 配 SOFT-INVALIDATE
  extractor_version : str                   # 重建版本化
```

> `ArcOp` 精确 schema 见 [arc-store](../stores/arc-store.md)；`WorldOp` 见 [world-store](../stores/world-store.md) 演化域。

## 不变式

1. 每个 op 的 `evidence` 必填，跨度不存在 = Faithfulness Check 系统硬拒（守 U）。
2. `t_valid = 本章`，Recorder 章末批写（亚章无意义）。
3. secret 不进 mem_ops——住 ArcStore 走 arc_ops（共用伏笔状态机 + knowledge as-of）。
4. REINFORCE/SOFT-INVALIDATE 必带 `target_id`（Reconciler 先检索旧条目）。
5. NOOP 留档供审计/幂等重建，Applier 只记日志不碰库。
6. 重建用低温/定种 + `extractor_version` 版本化，按 `(scope,type,归一化text)` 去重幂等。

## 交叉引用

- **源**：[script-store](../stores/script-store.md)（过闸 ChapterScript）。
- **落点**：memory-store / arc-store / world-store。
- **相减对象**：[plan-store](../stores/plan-store.md) L1（漂移度量）。
