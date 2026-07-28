# ArcStore（伏笔 / 主线 / secret 台账）

> **权威源**：本文件。ARCHITECTURE §11.7 留索引指针。
> **类型**：Store（**派生投影**：Script 的有损索引，可版本化重建）
> **ID 前缀**：`fs.{slug}` / `sec.{slug}` / `th.{slug}`（→ [ids](../primitives/ids.md)）

## 摘要

装三类**长程依赖账本**（伏笔、主线进度、秘密）。延续"一种结构靠 `kind` 区分"哲学（同 [memory-store](./memory-store.md)），三类合一张 `ArcRecord`、共享状态机、各带专属块。与 L1 意图相减 = 漂移信号。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | Architect | L1 创世 | thread / core 伏笔从 L1 铸 id 落台账（PLANNED） |
| 修改 | Recorder → Applier | 章末 | 消费 RecorderOutput.arc_ops，状态转移 + evidence |
| 晋升 | Recorder 提名（is_new+draft）→ Replanner 确认 | 卷末 | emergent 正式入账，回填 L1 |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Planner | 到期/临期伏笔、thread 进度 | 定本章该埋/收什么 |
| Continuity Critic | FULFILL 前有无 PLANT、secret.knowledge | 结构守卫 / 认知边界穿帮 |
| Character 装配 | secret.knowledge（as-of，POV 过滤） | 认知边界（他该不该知道） |
| Replanner | 全量 vs L1 | 漂移度量、loose-ends 报告 |

## 字段

```
ArcRecord:                                 # ArcStore 统一记录，kind 判别
  id              : fs.{slug} | sec.{slug} | th.{slug}
  kind            : foreshadow | secret | thread
  desc            : str
  origin          : planned(源自 L1) | emergent(生产中冒出，提名晋升)
  established_ch   : c{n}
  history         : { ch: c{n}, transition: str, evidence: EvidenceSpan[] }[]   # 时间线，as-of 回溯
  extractor_version : str                    # 派生投影，版本化重建
  # —— 伏笔 / 秘密 共享状态机 ——
  importance      : core | major | minor      # fs/secret
  state           : PLANNED|PLANTED|REINFORCED|FULFILLED|ABANDONED
  payoff_deadline : {granularity: chapter|volume|saga, ref}?   # L1 派生，Replanner 收紧
  plant_evidence  : EvidenceSpan[]            # 可多处=反复铺垫
  fulfill_evidence: EvidenceSpan[]
  abandon_reason  : str?                       # ABANDONED 必填，绝不静默悬空
  linked_thread   : th.{slug}?
  # —— secret 专属 ——
  knowledge       : { char: char.{slug}, since_ch: c{n}, evidence: EvidenceSpan[] }[]?
                                              # as-of 知情名单；hidden_from = 补集（隐式）
  # —— thread 专属 ——
  thread_state    : OPEN|ADVANCING|CLIMAX|RESOLVED|DROPPED?
  tier            : main | saga | local?       # 承 L1.threads.tier（撑 1000+ 章）
  advances        : { ch: c{n}, milestone: str, evidence: EvidenceSpan[] }[]?

ArcOp:                                      # RecorderOutput.arc_ops 的元素
  target_id     : fs.{slug} | sec.{slug} | th.{slug}
  kind          : foreshadow | secret | thread
  op            : PLANT | REINFORCE | FULFILL | ABANDON    # fs/secret 状态机
                | REVEAL                                    # secret 知情变更
                | ADVANCE | CLIMAX | RESOLVE | DROP         # thread 进度
  evidence      : EvidenceSpan[]              # 【必填】守 U
  abandon_reason?: str                         # ABANDON/DROP
  reveal_to?    : char.{slug}[]               # REVEAL：新增知情人（追加 knowledge）
  milestone?    : str                          # ADVANCE 描述
  is_new?       : bool                         # emergent 提名（新建 record，待 Replanner 确认）
  draft?        : { desc, kind, importance?, tier? }   # 新建时草稿定义
```

### 状态机

```
伏笔/秘密:  PLANNED ─plant─▶ PLANTED ─reinforce*─▶ (PLANTED/REINFORCED) ─fulfill─▶ FULFILLED〔终〕
            任意非终态 ─abandon(理由)─▶ ABANDONED〔终〕
秘密额外:   REVEAL 追加 knowledge（谁何时知情），不改主状态
主线:       OPEN ─advance*─▶ ADVANCING ─▶ CLIMAX ─resolve─▶ RESOLVED〔终〕
            任意非终态 ─drop(理由)─▶ DROPPED〔终〕
```

## 不变式

1. 每个 ArcOp 的 `evidence` 必填（守 U）。
2. ABANDONED/DROPPED 必带理由，绝不静默悬空（终局 loose-ends 保证）。
3. secret 知情用单列表 `knowledge[]`，"第 N 章谁知道"= `since_ch ≤ N` 集合，hidden_from 隐式补集。
4. emergent 记录经 Recorder 提名（`is_new+draft`）→ Replanner 卷复盘确认才 origin=emergent 正式入账并回填 L1。
5. thread 记录是 L1 意图的**实际进度投影**（id 同 `th.{slug}`），与 L1 计划相减 = 主线漂移。

## 收束保证（防悬空）

### 临期 / 逾期计算

`payoff_deadline = {granularity, ref}`：

| granularity | 到期下界（inclusive） | 临期窗口 |
|-------------|---------------------|---------|
| chapter | `ref` 的章号（`c12` → 12） | 到期前 2 章 |
| volume | 该卷 `chapter_range` 末章；若未知则该卷 L2 `chapter_beats` 最大 `planned_seq` | 卷内最后 3 章 |
| saga | 该篇覆盖卷的末章 | 篇内最后一卷 |

- **due（临期）**：`deadline_ch - window ≤ chapter < deadline_ch` 且未终态
- **overdue（逾期）**：`chapter ≥ deadline_ch` 且未终态（FULFILLED/ABANDONED）

Planner 每章拿 `due + overdue` 清单，强提示优先收。

### 逾期升级（按 importance）

| importance | 逾期动作 |
|------------|---------|
| minor | 卷复盘可 auto-reschedule 或 abandon（须理由） |
| major | 显式决策留痕（LooseEnd.recommendation），不可静默 |
| **core** | **逾期即 BLOCK 呼人**；Consistency Gate / Replanner 均不可自动废 |

### 终局收束

进最后一卷前，Replanner 生成 loose-ends report——所有非 FULFILLED/ABANDONED 伏笔必须排进终卷或显式 ABANDON。

## 交叉引用

- **写入增量**：[recorder-output](../artifacts/recorder-output.md) 的 `arc_ops`。
- **意图源**：[plan-store](./plan-store.md) L1（foreshadow_map / threads）。
- **配合**：[memory-store](./memory-store.md)（secret 认知边界）；[script-store](./script-store.md)（ChapterScript.foreshadow_ops）；[replanner](../../nodes/planning/replanner.md)。
