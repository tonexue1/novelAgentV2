# ViolationLog（违规报告 + 升级阶梯生命周期）

> **权威源**：本文件。ARCHITECTURE §11.9 留索引指针。
> **类型**：Store（**日志**：独立 append-only）
> **ID 前缀**：`vio.{ulid}`（→ [ids](../primitives/ids.md)）

## 摘要

一致性闸（硬检 + Continuity Critic）产出的结构化违规。承载"当前级重试 → 沿阶梯升级 → 降级放行/挂起"的全生命周期，反复失败即喂 Replanner 的漂移信号。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | 无 | — | 纯 append，无全局初始化 |
| 硬检违规 | Hard-Check（系统） | 每个生成节点后即时 | 可判定项当场拦 |
| 软判违规 | Continuity Critic（LLM） | 每场 Script 完成后 | OOC/穿帮/逻辑/语气 |
| 生命周期更新 | Gate/Orchestrator | 每次重试/升级 | 更新 history、resolution |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Orchestrator | open 违规 + severity | 驱动重试/升级阶梯 |
| Replanner | 聚合 category/refs 的 open/blocked | 漂移信号、卷复盘 |
| 人工 | blocked/flagged | 挂起处理、事后编辑真相层 |

## 字段

```
Violation:
  id              : vio.{ulid}          # Gate/HardCheck 铸
  chapter         : c{n}
  stage           : planner | director·setup | director·dispatch | character
  check_type      : hard | llm          # 系统硬检 / Continuity Critic
  severity        : BLOCK | CORRECT | ADVISORY
  category        : alive_present | location | timeline | ability | ref_integrity |
                    foreshadow_order | POV | OOC | canon_contradiction | voice | logic | other
  locus           : { chapter: c{n}, scene?: c{n}.s{m}, beat?: c{n}.s{m}.b{k}, obligation?: c{n}.s{m}.o{k} }
  script_evidence : EvidenceSpan[]       # 犯规落点（哪拍/哪场犯的）
  refs            : entity_id[]          # 违背了哪些既有条目（mem/world/arc id）
  message         : str                  # 人读描述
  suggestion?     : str                  # LLM 评审可选给出的修法建议
  # —— 升级阶梯生命周期（留痕 + 喂 Replanner 漂移信号）——
  escalation_level : beat | scene | chapter | volume
  retry_count      : int
  resolution       : open | fixed | flagged | blocked | advised   # 终态
  history          : { level, attempt: int, outcome: str }[]      # 阶梯轨迹
```

## 语义对齐（§3.5）

- **BLOCK** 爬满 → `blocked`（挂起该章 + 呼人；顺序递推不跳章）。
- **CORRECT** 耗尽 → `flagged`（标记放行，写 [script-store](./script-store.md) `ChapterScript.consistency_status`）。
- **ADVISORY** → `advised`（只记不重试）。
- 升级阶梯 `beat→scene→chapter→volume` 映到 `escalation_level`，`history[]` 记每级重试轨迹。

## 不变式

1. 独立 append-only 日志，不改写只追加（可观测 + 供 Replanner 聚合漂移信号）。
2. 单条 Violation 从 `open` 追到终态，重试走 `history[]` 不新开条目。
3. `script_evidence`（犯处）与 `refs`（被违背者）双指分开。
4. BLOCK 永不静默入库，爬满阶梯仍不过则挂起该章 + 呼人。
5. category 枚举 + `other` 兜底，新型违规先归 other 再固化。

## 交叉引用

- **检点来源**：[script-store](./script-store.md)（beat/scene 落点）、[world-store](./world-store.md) / [arc-store](./arc-store.md) / [memory-store](./memory-store.md)（被违背的 refs）。
- **升级顶端**：[plan-store](./plan-store.md)（Replanner 卷复盘 = 阶梯第④级）。
