# 公共基元（EvidenceSpan / StoryTime / 枚举）

> **权威源**：本文件。ARCHITECTURE §11.0 留索引指针。
> **类型**：Primitive（公共基元）

## 摘要

跨多个 schema 复用的小结构与共享枚举，集中定义一处，避免各文件散抄漂移。

## 生产 / 消费

无独立生产者——作为字段类型嵌入各 store/artifact。凡需出处的字段一律用 `EvidenceSpan[]`。

## 字段

### EvidenceSpan（守 U 的寻址基元）

```
EvidenceSpan:
  chapter : int          必填
  scene   : int?          省略 = 整章（罕见）
  beats   : [from,to]?    省略 = 整场
```

简写串：`c12.s3.b5` / `c12.s3.b5-8`（第 5~8 拍）/ `c12.s3`（整场）/ `c12`（整章）。
凡需 `evidence` 的字段类型 = **`EvidenceSpan[]`**（一条可引多处，如反复铺垫）。

**硬约束**：每个 span 必须解析到已提交的 ScriptStore 位置（系统硬检 = 忠实性校验第一关，守 U）。

### StoryTime（叙事内时间，供时间线硬检）

```
StoryTime:
  day?      : int         第几天（叙事内）
  clock?    : str         "黄昏" / "三更" / "10:30"
  relative? : str         "三日后" / "同一时刻"
```

### as-of 主时钟

`chapter`（int）：`t_valid / t_invalid / knowledge.since_ch` 全部 chapter 粒度（Recorder 章末批写，亚章无意义）；`evidence` 可细到 beat 记出处，但有效性时间线只到章。

### 共享枚举

```
severity     : BLOCK | CORRECT | ADVISORY          # → violation-log
importance   : core | major | minor                # 伏笔/世界实体重要度
tier(world)  : core | major | minor                # → world-store
tier(char)   : 0 | 1 | 2 | 3                        # → memory-store（画像完整度/检索降权）
detail_level : sketch | detailed                    # → plan-store 滚动地平线
resolution   : achieved | abandoned | superseded    # 记忆软失效原因
```

## 交叉引用

- `EvidenceSpan` 引用位置 id → [ids](./ids.md)。
- 被 script-store / memory-store / arc-store / world-store / summary-store / violation-log 广泛引用。
