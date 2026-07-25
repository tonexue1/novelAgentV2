# Director·setup（拆场定合同）

> **层**：production ｜ **类型**：LLM ｜ **触发**：每章（L3 之后）
> **提示词**：待定（本文先略）

## 做什么

把 ChapterPlan 拆成若干场景**合同**：定舞台（地点/时间/在场）+ 戏剧框架（目标/冲突/POV）+ **承重拍 obligations**（必命中的锚，无序）+ 退出条件。**不预排 turn 顺序**（那是 dispatch 的运行时活）。铸 scene id。

## 入参

- [chapter-plan](../../schema/artifacts/chapter-plan.md)（L3）：cast/story_beats/constraints/background_hint。
- [world-store](../../schema/stores/world-store.md)：loc+地理关系、在场 org、相关 art/concept/item（搭 canon 底座）。
- 出场角色粗画像 → [memory-store](../../schema/stores/memory-store.md)；相关旧场景情境（scene 摘要）→ [summary-store](../../schema/stores/summary-store.md)。
- 上下文由 [assembler](../system/assembler.md) 按**中分辨率**装配。

## 输出

- [scene-script](../../schema/artifacts/scene-script.md) SceneScript（`SceneContract[]` + `Obligation[]`）。
- 铸 `c{n}.s{m}` scene id + `c{n}.s{m}.o{k}` obligation id。

## 交互

- **上游**：[hard-check](../validation/hard-check.md)（L3 过检）。
- **下游**：[hard-check](../validation/hard-check.md)（合同过检）→ [director-dispatch](./director-dispatch.md) 现场调度。
- **检点**：查 WorldStore/ArcStore（地点存在、时间线、POV 在场）。

## 要害

承重拍完备但不定序；`background_hint` 群体龙套在此现场引入+命名。
