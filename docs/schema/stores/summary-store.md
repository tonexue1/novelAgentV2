# SummaryStore（多分辨率摘要索引）

> **权威源**：本文件。ARCHITECTURE §11.8 留索引指针。
> **类型**：Store（**派生投影**：Script 的多分辨率有损投影，可版本化重建）
> **键**：`(level, ref)` 定位键（→ [ids](../primitives/ids.md)）

## 摘要

Script 的多分辨率派生投影，专治"1000+ 章没法全塞上下文"的长程检索难题——检索**加速层**，非真相（真相永在 [script-store](./script-store.md)）。近段命中原文、远段命中章/卷/篇摘要，按 token 预算"越远越压缩"。是 FOUNDATION 的 skip-connection。

## 生产（谁写）

| 动作 | level | 节点 | 时机 |
|------|-------|------|------|
| 初始化 | — | 无 | 随章/卷推进增量产出 |
| 修改 | scene / chapter | Summarizer | 章末（对齐 L3） |
| 修改 | volume | Replanner | 卷末（对齐 L2/L1） |
| 修改 | saga | Replanner | 篇末（对齐 L1.sagas） |

写入走**独立 SummaryDelta**（Applier 章末/卷末落库），不并入 RecorderOutput。

## 消费（谁读）

| 节点 | 取哪层 | 用途 |
|------|--------|------|
| Planner | 章/卷摘要（粗） | 定本章方向，不要 beat 细节 |
| Director·setup | scene 摘要（中） | 搭情境 |
| Continuity Critic | 流水桶语义检索 | 防穿帮 |
| Character 装配 | 本章更早场滚动摘要 | 工作缓冲（当前场才逐拍原文） |

## 字段

```
SummaryEntry:                          # 多分辨率摘要，Script 派生投影（守 D）
  level         : scene | chapter | volume | saga
  ref           : c{n}.s{m} | c{n} | v{k} | sg{j}    # 所概括的定位单元（level+ref 唯一键）
  text          : str                   # 蒸馏梗概（检索命中的"粗上下文"）
  vec           : embedding             # 建在 text 上（语义检索对象=摘要，低噪）
  covers        : EvidenceSpan[]        # 概括了哪些源单元（逐层收敛：saga→vol→ch→scene→原文 beat）
  # —— 轻结构化 facet（filter-then-rank）——
  threads       : th.{slug}[]           # 涉及主线（先过滤再语义排）
  cast          : char.{slug}[]         # 涉及角色
  key_ops       : { op, id }[]?         # 本段伏笔/主线关键操作（可选）
  # —— 元 ——
  t_valid       : c{n}                  # 产出章（volume/saga 记卷/篇末章）
  produced_by   : Summarizer | Replanner
  summarizer_version : str              # 版本化重建（守 D）

SummaryDelta:                          # Summarizer/Replanner → Applier，独立于 RecorderOutput
  chapter       : c{n}                  # 产出章（volume/saga 记卷/篇末章号）
  entries       : SummaryEntry[]        # 一批幂等 upsert；(level,ref) 已存在则替换并升 summarizer_version
  produced_by   : Summarizer | Replanner
```

## 检索用法

```
facet 过滤（threads/cast）→ 摘要 vec 语义排 → 按 token 预算选层级（近细远粗）→ 需精确则顺 covers/evidence 钻原文
```

三路召回互补：情境相似→摘要 embedding；具体事实→结构化 fact（memory-store）；已知回调→evidence 指针。

## 不变式

1. `(level, ref)` 唯一键，幂等替换 + `summarizer_version` 版本留痕。
2. `vec` 只建在 `text`（摘要即 embed 对象，低噪少量）。
3. `covers` 逐层收敛，scene 级才回指原文 beat。
4. 派生投影可版本化重建（低温/定种，守 D），Script 为地面真相。

## harness 评估指标（后续）

摘要**保真度**（vs 源场景蕴含，守 D 抽样）、**长程召回**（远期伏笔/事实能否经摘要层被检回）、**压缩率 vs 信息损失**、检索**命中层级分布**是否随距离合理下沉。

## 交叉引用

- **源**：[script-store](./script-store.md)（scene/chapter）。
- **产出者**：Summarizer / Replanner（→ [plan-store](./plan-store.md) 层级对齐）。
- **协同召回**：[memory-store](./memory-store.md)、[arc-store](./arc-store.md)。
