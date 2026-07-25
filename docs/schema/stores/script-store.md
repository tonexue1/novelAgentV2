# ScriptStore（剧本，主真相）

> **权威源**：本文件。ARCHITECTURE §11.1 留索引指针。
> **类型**：Store（**主真相**：冻结、只追加、过 B 闸、bit 级可复现）
> **ID 前缀**：位置 id `c{n}` / `c{n}.s{m}` / `c{n}.s{m}.b{k}`（→ [ids](../primitives/ids.md)）

## 摘要

媒介无关的中间表示（IR），生产层与消费层的中心契约。由四职责逼出：〔媒介无关契约〕〔主真相/证据靶子〕〔递推时钟〕〔控制流骨架〕+ 账本接口〔漂移账〕〔认知边界〕。三层 `ChapterScript > Scene > Beat`。**其余一切记忆/台账/摘要都是它的派生投影。**

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | 无（每章新建） | — | 章级只追加，无全局初始化 |
| beat 涌现 | Character（实现段）+ Director·dispatch（派工段） | 逐拍运行时 | 内容自主 + 流向可控 |
| 落库定序 | Applier | 过一致性闸后 | 铸 beat id、写入 ScriptStore |

> **没过闸的内容不许进 ScriptStore**（§3.5 闸门纪律）。

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Recorder（Extractor） | 过闸 ChapterScript 全文 | 抽取记忆/伏笔增量（→ recorder-output） |
| Summarizer | ChapterScript | 产 scene/chapter 摘要（→ summary-store） |
| 消费层 Writer/VLM | ChapterScript | 渲染为散文/分镜（成品层） |
| 一切 evidence 回指 | beat/scene 位置 | 派生投影的出处校验（守 U） |

## 字段

```
ChapterScript:
  id                 : c{n}                      # = as-of 主时钟
  volume             : v{k}
  theme              : str
  covered_threads    : th.{slug}[]
  foreshadow_ops     : {op: PLANT|REINFORCE|FULFILL, fs_id}[]   # 本章实际伏笔操作
  tone               : str
  consistency_status : clean | flagged           # 过闸标记（§3.5）
  derived_from       : chapter_plan_ref          # 追溯 L3（→ artifacts/chapter-plan）
  scenes             : Scene[]

Scene:
  id            : c{n}.s{m}
  location      : loc.{slug}                      # 引 WorldStore，硬检存在性（→ world-store）
  time          : StoryTime                        # 供时间线硬检（→ common）
  mood          : str                              # 氛围/天气（VLM 用）
  pov           : char.{slug}
  goal          : str
  conflict      : str
  cast          : { char: char.{slug}, entry_state: str }[]
  contract_ref  : scenescript_scene_id             # 回指场景合同（→ artifacts/scene-script）
  beats         : Beat[]                           # 运行时涌现，Applier 落库定序

Beat:
  id            : c{n}.s{m}.b{k}                   # evidence 主要落点；自身不带 evidence
  # —— 派工段（Director·dispatch 铸，持久化作证据链）——
  owner         : char.{slug} | ENV | NARRATION
  dramatic_goal : str                              # "逼X摊牌"级；schema 焊死：禁台词
  hits          : obligation_id?                   # 命中的承重拍（→ artifacts/scene-script）
  # —— 实现段（Character 填，按 type 分支）——
  type          : dialogue | action | thought
  dialogue?     : { line: str, subtext?: str, tone?: str }
  action?       : { stage: str }
  thought?      : { inner: str }
  # —— handoff（喂下一次 dispatch，非渲染字段）——
  handoff?      : { kind: ADDRESS|DEMAND|EXIT|NONE, target?: char.{slug} }
```

## 不变式

1. beat 是真相靶子，自身无 evidence（被派生层引用）。
2. `dramatic_goal` 只含戏剧目标不含台词（内容/流向分权的焊点）。
3. scenes/beats 只追加，位置 id 提交后不可变。
4. ENV/NARRATION 拍无 dialogue、仅 action/thought 段承载环境事件/旁白。

## 交叉引用

- **上游**：[scene-script](../artifacts/scene-script.md)（合同 + 派工）、[chapter-plan](../artifacts/chapter-plan.md)（derived_from）。
- **下游**：[recorder-output](../artifacts/recorder-output.md) → memory/arc/world 派生；[summary-store](./summary-store.md)。
- **相关**：[violation-log](./violation-log.md)（过闸留痕）。
