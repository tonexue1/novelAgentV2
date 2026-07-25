# MemoryStore（人物记忆，派生投影）

> **权威源**：本文件。ARCHITECTURE §7 留索引指针。
> **类型**：Store（**派生投影**：有损、LLM 抽取、可版本化重建，每条挂 evidence）
> **ID 前缀**：条目 `m.{ulid}`；`scope` 用 `char.{slug}` / `th.{slug}` / global（→ [ids](../primitives/ids.md)）

## 摘要

所有人物相关记忆一种结构，靠字段区分用途。核心二分：**画像（语义记忆，有界，全取快照）** vs **经历（情节记忆 fact，无界，选择性检索）**。是 ScriptStore 的派生投影，非独立真相。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | Architect | L1 创世 | tier 0/1 主角画像种子（可选） |
| 修改 | Recorder（Extractor→Faithfulness→Reconciler）→ Applier | 章末 | 消费 RecorderOutput.mem_ops |
| 软失效 | Reconciler → Applier | 章末 | SOFT-INVALIDATE 设 t_invalid，不删 |
| tier 重定级 | Recorder 提名 → Replanner 确认 | 卷末 | as-of 回填 |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Character 装配 | 单角色画像(全取) + voice 例句 + 关系触发经历 + goal 栈 | 演戏（POV 过滤，认知边界） |
| Continuity Critic | as-of 人设 + 能力台阶 | OOC / 能力越级查错 |
| Planner/Director | 粗画像、goal | 情节/场景决策 |
| Replanner | goal/trait 轨迹 vs L1 意图 | 角色弧线漂移度量 |

## 字段

**统一字段**（靠字段区分用途）：

```
MemoryEntry:
  id          : m.{ulid}
  type        : fact | belief | trait | voice | ability | goal
  scope       : char.{slug} | th.{slug} | global      # 命名空间，检索过滤
  text        : str
  vec         : embedding
  t_valid     : chapter                                # → common（as-of 主时钟）
  t_invalid?  : chapter                                # 软失效
  strength?   : float                                  # 信念/性格程度/执念
  evidence    : EvidenceSpan[]                         # 【必填】守 U（→ common）
  involves?   : entity_id[]                            # 牵涉实体，关系触发检索前提（fact 用）
  salience?   : float                                  # 显著度，抗 recency 淹没（fact 用）
  resolution? : achieved | abandoned | superseded      # 软失效原因（goal/伏笔用）
  # type 专属
  goal_kind?    : long-drive | stage-goal              # goal
  parent?       : m.{ulid}                             # goal 层级链
  example?      : str                                  # voice 真实台词例句（few-shot 库）
  tier?         : 0 | 1 | 2 | 3                        # 角色分层（画像完整度/检索降权）
  ability_rank? : int                                  # ability 台阶序（越高越强）；修为单调硬检直接比较此值
```

### 画像 vs 经历（取法相反）

| type | 有界? | 取法 |
|------|------|------|
| trait / ability / goal | 有界 | **全取** as-of 快照 |
| belief | 半有界（累积） | 取活跃；过多按 `strength × 相关性` 挑 |
| voice | profile 有界 + 例句无界 | profile 全取 + 例句语义挑 few-shot |
| **fact（经历）** | **无界（逐章疯长）** | **选择性检索**（人设桶经历子桶） |

### 六类存法

- **trait**：对立维度打分（慈悲↔狠戾=-0.8）+ 章节时间线。
- **belief**：信念陈述 + 强度 + 证据 + 软失效。
- **voice**：风格摘要 + 真实台词例句库（`example`，靠 few-shot 不靠形容词）。
- **ability**：等级台阶 + 时间线（配 world-store 境界 canon + 单调硬检）。台阶用 `ability_rank`（整数序）承载，Hard-Check 按 as-of 比较其非降（越级战斗是软判，见 EVALUATION A3）。
- **goal**：多尺度（long-drive / stage-goal；场景意图不持久走 scene-script）+ `parent` 层级链 + 生命周期（软失效 + resolution）。长期 drive 意图在 L1.character_arc，实际轨迹在此，相减=角色弧线漂移。
- **fact**：发生过什么 + involves + salience；蒸馏版，evidence 指回原文（双分辨率）。

## 不变式

- `evidence` 必填（守 U）；`t_valid=本章`。
- 软失效不删（设 t_invalid + resolution）。
- 秘密不在此——住 [arc-store](./arc-store.md)（`kind=secret`，共用伏笔状态机 + knowledge 认知边界）。
- 派生投影可版本化重建（低温/定种），Script 为地面真相。

## 交叉引用

- **写入增量**：[recorder-output](../artifacts/recorder-output.md) 的 `mem_ops`（MemOp）。
- **相减对象**：[plan-store](./plan-store.md) L1（goal/arc 意图）。
- **配合**：[arc-store](./arc-store.md)（secret 认知边界）、[world-store](./world-store.md)（ability 阶梯）。
