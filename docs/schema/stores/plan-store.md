# PlanStore（L0 / L1 / L2，意图锚 P）

> **权威源**：本文件。ARCHITECTURE §11.2 留索引指针。
> **类型**：Store（**意图**：慢变、版本化）
> **ID**：`L0`（单例冻结）/ `L1@v{n}` / `L2.v{k}@v{n}`（→ [ids](../primitives/ids.md)）

## 摘要

意图层，唯一目的：给"实际"（ArcStore/MemoryStore）一个**可相减的意图基准**，自上而下逐级细化。**为撑到 1000+ 章**，L1 内建三件套：`sagas[]`（篇分组）、`detail_level`（滚动地平线）、`threads.tier`（主线分层）。L1 也是防漂移主锚，铸 `th./fs./char.` 三类实体 id。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | Architect（+ Worldbuilder 协同） | 创世一次 | L0（独占冻结）+ L1(v1) + L2[卷1]；人工种子驱动 |
| 修改·进度/修订 | Replanner | 卷边界 | L1 进度更新 / 结构性修订(v+1，人工关卡) |
| 修改·下一卷 | Replanner | 卷边界 | 滚动生成 L2[下一卷]、sketch→detailed 滚出 |

> 人工关卡只在两处：(a) 初始 L1，(b) L1 结构性修订(v+1)。L2 滚动生成全自动。

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Planner | L0/L1/L2 + 到期伏笔 due list | 定本章方向（→ chapter-plan） |
| Replanner | L1 意图 vs 实际（Arc/Memory） | 漂移度量、loose-ends |
| Continuity Critic | L1 结构约束 | 结构守卫 |
| Worldbuilder | L0/L1 引用的 world id | 造 canon 时对齐 |

## 字段

```
L0  (单例, 创世冻结; 改=换书):
  logline, genre, themes[], tone, target_length, media,
  core_dramatic_question, ending_intent,
  protagonist_arc_intent : str[]        # 纯文字，无 id

L1  {version, created_at_ch, status}:   # 整份快照版本化；防漂移主锚；铸 th./fs./char. 三类 id
  sagas[]          : {saga_id: sg{k}, title, volume_range, goal,
                      saga_turning_point?, detail_level: sketch|detailed}   # 篇（超长篇分组）
  volumes[]        : {vol_id: v{k}, saga_id?: sg{k}, title, chapter_range(计划,粗),
                      goal, detail_level: sketch|detailed}
  threads[]        : {thread_id: th.{slug}, tier: main|saga|local, parent_thread_id?: th.{slug},
                      desc, start_ch, target_ch, milestones[{desc, target_vol}]}
  character_arcs[] : {char_id: char.{slug}, from_state, to_state, key_shifts[]}   # 仅收录 tier 0/1
  turning_points[] : {desc, target_vol}
  foreshadow_map[] : {fs_id: fs.{slug}, desc, plant_range,
                      payoff_deadline: {granularity: chapter|volume|saga, ref},   # 粗粒度可埋，Replanner 逐步收紧
                      importance: core|major|minor}
  pacing_curve?    : ...

L2  {vol_id, version}:                   # 每卷；滚动生成
  goal
  thread_targets[]    : {thread_id, target_milestone}
  foreshadow_due[]    : {fs_id, action: plant|fulfill}       # → 派生 due list 喂 Planner
  character_targets[] : {char_id, target_state}
  chapter_beats[]     : {planned_seq: int, gist: str}         # 粗，每章一句；不绑 c{n}
  entries[]           : {char_id, planned_seq}
  exits[]             : {char_id, planned_seq}
  climax_position     : ...
```

## 约束

- `character_arcs` **仅收录 tier 0/1**（主角 + 跨篇核心）；龙套/单篇角色弧线不进 L1，其画像归 [memory-store](./memory-store.md)，`tier` 是 MemoryStore 字段。
- `foreshadow_map.payoff_deadline` 支持**粗粒度**：core 超长伏笔埋时可只标 `saga` 级，Replanner 逐步收紧成 `volume`→`chapter`。临期判定用粒度下界。
- **滚动地平线（1000+ 章命门）**：只冻 L0（终点）+ L1 篇级骨架 + core 伏笔；近段 `detail_level=detailed`，远段 `sketch`（一句 gist）。意图固定、细节 JIT，漂移闭环保证朝 L0 收敛。
- **决定**：① L0 纯立意无 id、id 一律 L1 铸；② L2.chapter_beats 用 `planned_seq` 占位、不绑 `c{n}`；③ L1 整份快照版本化。

## 配套（不在 PlanStore，登记于此）

- 境界/力量阶梯 = [world-store](./world-store.md) canon 阶梯 + [memory-store](./memory-store.md) ability 台阶 + 单调硬检（只增不跳级=BLOCK）。
- 角色分层 `tier 0~3` = MemoryStore 字段（决定画像完整度与检索降权）。

## 交叉引用

- **下游**：[chapter-plan](../artifacts/chapter-plan.md)（L3 派生自 L2）。
- **相减对象**：[arc-store](./arc-store.md)（thread/fs 实际）、[memory-store](./memory-store.md)（goal/trait 实际）→ 漂移度量。
