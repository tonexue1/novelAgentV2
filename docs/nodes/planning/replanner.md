# Replanner（卷复盘师）

> **层**：planning ｜ **类型**：LLM ｜ **触发**：卷 / 篇边界；一致性闸第④级（volume）
> **提示词**：待定（本文先略）

## 做什么

卷边界复盘：先**诊断漂移**（实际 vs 意图），再**带约束修正**。默认只改下一卷 L2 把剧情拽回；仅当 L1 里程碑不可达 / 出现更优涌现才提 L1 结构性修订(v+1)。同时产 volume/saga 摘要、loose-ends 报告，确认 emergent 伏笔与人物 tier 晋升。

## 入参

- 意图：[plan-store](../../schema/stores/plan-store.md) L1 + 本卷 L2。
- 实际：[arc-store](../../schema/stores/arc-store.md)（thread/fs 进度）、[memory-store](../../schema/stores/memory-store.md)（goal/trait 轨迹）。
- [violation-log](../../schema/stores/violation-log.md)：反复失败的 category/refs 聚合（漂移信号）。
- 待确认：Recorder 的 emergent 伏笔提名、`tier_noms`（→ [recorder-output](../../schema/artifacts/recorder-output.md)）。
- 确定性预计算：`DriftReport`（见下，系统侧先算再喂 LLM）。

## 输出

```
ReplannerOutput:
  drift_report      : DriftReport           # 系统预计算 + LLM 注释
  action            : patch_l2 | revise_l1 | hold
  l2_next?          : L2                    # patch_l2：下一卷详细规划
  l1_revision?      : L1                    # revise_l1：结构性修订(v+1)，须人工确认后落库
  volume_summary    : SummaryEntry          # level=volume
  saga_summary?     : SummaryEntry          # 篇末才有
  loose_ends        : LooseEnd[]
  confirmed_tiers   : TierNom[]             # 确认后交 Applier.apply_tier_noms=True
  confirmed_emergent: str[]                 # 确认的 emergent arc / world id
  world_promote     : { entity_id, to_tier }[]  # 唤 Worldbuilder 补 definition
  human_gate?       : str                   # 非空 = 必须人工确认才能继续
```

### DriftReport（漂移度量）

| 指标 | 定义 | 阈值建议 |
|------|------|---------|
| thread_lag | L1.threads 中 milestone 计划章 vs ArcStore.advances 实际章的延迟章数均值 | 每卷 |
| foreshadow_overdue_rate | 逾期未收伏笔数 / 活跃伏笔数 | 每卷 |
| goal_drift | MemoryStore goal 栈 vs L1.character_arcs 意图的文本/语义偏离（LLM 评 0~1） | 每卷 |
| violation_density | 本卷 Violation 数 / 章数 | 每卷 |

频率：**默认每卷一次**；若 `violation_density > 2.0` 或 Consistency Gate 升级到 volume，则提前触发。

### L2 修正 vs L1 修订触发判据

| 条件 | 动作 |
|------|------|
| thread_lag ≤ 2 且 overdue_rate < 0.3 且无 core 逾期 | **hold** 或轻量 **patch_l2**（只调下一卷 beat） |
| thread_lag > 2 或 overdue_rate ≥ 0.3，但 L1 里程碑仍可达 | **patch_l2**（默认） |
| L1 里程碑不可达 / 更优涌现需改全书结构 / core 伏笔必须改 deadline | **revise_l1**(v+1) + `human_gate` |
| core 伏笔逾期 | **BLOCK 呼人**（不许自动漂/废），`human_gate` 必填 |

### LooseEnd

```
LooseEnd:
  id          : fs.{slug} | th.{slug} | sec.{slug}
  kind        : foreshadow | thread | secret
  status      : open | overdue | at_risk
  importance  : core | major | minor
  recommendation : fulfill_in_next_vol | reschedule | abandon | human
  reason      : str
```

## 交互

- **上游**：卷边界定时（orchestrator/walk 检测卷末）/ 一致性闸升级阶梯第④级 `escalate_volume`。
- **下游**：[planner](./planner.md) 消费更新后的 L1/L2；[applier](../system/applier.md) 落 summary + tier；[worldbuilder](./worldbuilder.md) 补晋升定义。

## 要害

是宏观误差投影（接微观闸门顶端）。core 伏笔逾期 = BLOCK 呼人，不许自动漂/废。
