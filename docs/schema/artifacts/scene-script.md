# SceneScript（场景合同）+ BeatDispatch（派工）

> **权威源**：本文件。ARCHITECTURE §11.5 留索引指针。
> **类型**：Artifact（节点间消息）

## 摘要

`Director·setup` 产 **SceneScript**（合同：定锚不定序）→ `Director·dispatch` 逐拍产 **BeatDispatch** → Character 填实现段。合同被 `Scene.contract_ref` 回指，供 Critic **验承重拍履约**。核心：定锚（obligations）不定序，turn 顺序运行时涌现。

## 生产（谁写）

| Artifact | 节点 | 时机 | 说明 |
|----------|------|------|------|
| SceneScript | Director·setup | 每章拆场时 | 铸 scene id + obligations；随 ChapterScript 落 ScriptStore（只读契约快照） |
| BeatDispatch | Director·dispatch | 逐拍运行时 | 瞬态；Character 填实现段后 Applier 合进 Beat 派工段 |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Director·dispatch | obligations + exit_when + budget | 现场调度、判收场 |
| Character | BeatDispatch(owner+dramatic_goal) + cast.scene_goal | 演一拍 |
| Continuity Critic | obligations vs 实际 beats | 验承重拍履约 |

## 字段

```
SceneScript:                              # Director·setup 产；随 ChapterScript 持久化（只读契约快照）
  chapter        : c{n}
  derived_from   : chapter_plan_ref        # 追溯 L3（→ chapter-plan）
  scenes         : SceneContract[]

SceneContract:
  id             : c{n}.s{m}               # setup 铸 scene id；最终 Scene 同号
  location       : loc.{slug}              # 引 WorldStore，硬检存在性（→ world-store）
  time           : StoryTime               # → common
  pov            : char.{slug}
  goal           : str                     # 本场戏剧目标
  conflict       : str
  cast           : { char: char.{slug}, entry_state: str, scene_goal?: str }[]   # 参与者+入场状态+场级动机
  obligations    : Obligation[]            # 承重拍：必命中的锚，【无序】
  exit_when      : str[]                   # 退出条件（LLM 判；硬检兜底=承重拍全命中 | 撞 budget）
  budget         : { max_beats?: int }     # 撞预算强制收场
  grounding      : EvidenceSpan[]          # 依据（L3/记忆/world 出处）

Obligation:
  id             : c{n}.s{m}.o{k}          # ← Beat.hits 回指此 id（→ script-store）
  desc           : str                     # "张三逼李四摊牌身世"级；禁台词
  owner_hint     : char.{slug}?            # 建议主导者（非强制）
  precede        : obligation_id[]         # 偏序【软约束】：dispatch 尽量遵守，漏走升级阶梯
  binds          : {op: PLANT|REINFORCE|FULFILL, fs_id}?   # 绑定伏笔/主线 op（→ arc-store）

BeatDispatch:                             # Director·dispatch 逐拍产；瞬态
  scene          : c{n}.s{m}
  owner          : char.{slug} | ENV | NARRATION
  dramatic_goal  : str                     # 焊死禁台词
  hits           : obligation_id?          # 本拍要命中的承重拍
  directive?     : str                     # 给 owner 的额外调度提示（可选，简短）
```

## 不变式

1. 合同定锚（obligations）不定序，turn 顺序运行时由 dispatch 涌现。
2. `dramatic_goal`/`desc` 只含戏剧目标不含台词。
3. obligation id 场景内定位，`Beat.hits` 回指做履约审计。
4. BeatDispatch 不单独落库——Character 填实现段后 Applier 合进 `Beat` 派工段。
5. 退场硬检兜底：承重拍全命中或撞 budget 必收场。

## 交叉引用

- **上游**：[chapter-plan](./chapter-plan.md)（L3）。
- **下游**：[script-store](../stores/script-store.md)（Scene.contract_ref / Beat.hits）。
- **引用**：[world-store](../stores/world-store.md)（location）、[arc-store](../stores/arc-store.md)（binds）。
