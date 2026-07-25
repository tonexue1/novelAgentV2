# Schema（冻结权威）

本目录是数据流上每个 store 与节点间 artifact 的 **schema 单一真相源**。`ARCHITECTURE.md §11` 仅留索引指针，字段细节以本目录为准。冲突时以本目录为权威。

## 类型记法

`?`=可选 · `[]`=数组 · `|`=枚举 · `{}`=对象。

## 三类分层

- **primitives/**：坐标系与公共基元（ID、EvidenceSpan、StoryTime、公共枚举）。
- **stores/**：有状态存储（真相 / 派生投影 / 意图 / 日志）。
- **artifacts/**：节点间流转的无状态消息。

## 索引

| 文件 | § | 类型 | 一句话 |
|------|---|------|--------|
| [primitives/ids](./primitives/ids.md) | 11.0 | Primitive | 三类 id（位置/实体/不透明）+ 铸造责任 |
| [primitives/common](./primitives/common.md) | 11.0 | Primitive | EvidenceSpan、StoryTime、公共枚举 |
| [stores/script-store](./stores/script-store.md) | 11.1 | Store·主真相 | ChapterScript / Scene / Beat |
| [stores/plan-store](./stores/plan-store.md) | 11.2 | Store·意图 | L0 / L1 / L2 规划锚 P |
| [stores/world-store](./stores/world-store.md) | 11.4 | Store·canon | 世界圣经（概念/功法/地理/势力…） |
| [stores/memory-store](./stores/memory-store.md) | 7 | Store·派生 | 人物记忆（画像 vs 经历） |
| [stores/arc-store](./stores/arc-store.md) | 11.7 | Store·派生 | 伏笔 / 主线 / secret 台账 |
| [stores/summary-store](./stores/summary-store.md) | 11.8 | Store·派生 | 多分辨率摘要索引 |
| [stores/violation-log](./stores/violation-log.md) | 11.9 | Store·日志 | 违规报告 + 升级阶梯生命周期 |
| [artifacts/seed](./artifacts/seed.md) | 2.6 | Artifact·人工入口 | Seed（创世种子，创世唯一人工输入） |
| [artifacts/chapter-plan](./artifacts/chapter-plan.md) | 11.3 | Artifact | ChapterPlan（L3） |
| [artifacts/scene-script](./artifacts/scene-script.md) | 11.5 | Artifact | SceneScript + BeatDispatch |
| [artifacts/recorder-output](./artifacts/recorder-output.md) | 11.6 | Artifact | RecorderOutput / MemoryDelta / MemOp |

## 数据流阅读顺序

```
ids/common（坐标系）
  → plan-store（L0/L1/L2 意图）
  → chapter-plan（L3）
  → world-store（canon 底座）
  → scene-script（场景合同 + 派工）
  → script-store（主真相，过闸入库）
  → recorder-output（抽取增量）→ memory-store / arc-store / world-store（演化）
  → summary-store（摘要索引）
  → violation-log（贯穿全程的闸门留痕）
```

## 不变式速查

- **主真相唯一**：ScriptStore（只追加、过闸、bit 级）。Memory/Arc/Summary/World 演化域皆为**派生投影**（有损、evidence 回指、可版本化重建）。
- **evidence 必填**：一切派生条目须 `EvidenceSpan[]` 回指已提交的 ScriptStore 位置（守 U）。
- **as-of 主时钟 = chapter**：`t_valid / t_invalid / knowledge.since_ch` 全章粒度。
- **id 不可变，显示名可变**。
