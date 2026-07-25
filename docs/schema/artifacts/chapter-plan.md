# ChapterPlan（L3，意图→生产接口）

> **权威源**：本文件。ARCHITECTURE §11.3 留索引指针。
> **类型**：Artifact（节点间消息）

## 摘要

Planner 每章产出。使命：把 L2 粗章槽落成**本章可执行方向**，喂 Director·setup 拆场，并留追溯链给漂移度量。**只到章级义务，不映射到场**（拆场是 Director 的活）。命名卫生：章内粗桥段叫 `story_beats`，区别于 Script.beat（拍）与承重拍（obligation）。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | — | — | 无；每章新产一份 |
| 产出 | Planner | 每章开头 | 读 P(L0/L1/L2) + Arc 进度 + 到期伏笔 + 近章摘要 |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Director·setup | cast/story_beats/constraints | 拆场，产 SceneScript |
| Applier | 全份 | 作 ChapterScript.derived_from 追溯 |
| Replanner | derived_from vs 实际 | 漂移度量 |

## 字段

```
ChapterPlan:
  chapter           : c{n}                       # 生成时绑定的真实章 id
  derived_from      : {l2_vol_id: v{k}, planned_seq,
                       l1_thread_ids[], l1_fs_ids[]}          # 追溯（漂移度量）
  theme             : str
  tone              : str
  chapter_goal      : str                        # 章级收敛判据
  thread_advances   : {thread_id, milestone_ref?, intent}[]  # 推进哪条主线、到什么程度
  foreshadow_ops    : {fs_id, op: PLANT|REINFORCE|FULFILL,
                       reason: due|overdue|organic}[]         # 本章埋/收（含逾期收束）
  cast              : {char_id, role_in_chapter, required: true|false}[]
                      #   required=true  硬性出场（Director 不得删）
                      #   required=false 建议出场，Director 可裁
  background_hint   : str?                        # 群体占位，交 Director 自由填充+命名（默认 tier 3）
  entries / exits   : {char_id}[]                 # 本章进退场
  story_beats       : {seq, gist}[]               # 章内粗桥段（Director 拆场骨架）
  constraints       : str[]                       # 硬约束（如"不得提前揭 fs.wushi""X 本章不在场"）
```

## 分层发挥（casting 权限）

- Planner 只 cast 剧情相关角色（tier 0/1/2，required）。
- 背景龙套经 `background_hint` 下放 Director 现场引入+命名、Character 赋声，Recorder 章末登记 tier 3。
- 若反复出现，re-tiering 追认升级（→ [memory-store](../stores/memory-store.md) tier 机制）。
- **三个"拍"层层细化**：`story_beats`（章内桥段，Planner）→ 承重拍 obligation（场内锚，Director）→ `Beat`（一拍，Character）。

## 交叉引用

- **上游**：[plan-store](../stores/plan-store.md)（L2 派生）。
- **下游**：[scene-script](./scene-script.md)（Director·setup 拆场）、[script-store](../stores/script-store.md)（derived_from）。
- **引用**：[arc-store](../stores/arc-store.md)（fs/thread id）。
