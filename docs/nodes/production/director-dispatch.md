# Director·dispatch（现场调度）

> **层**：production ｜ **类型**：LLM（小/快）｜ **触发**：逐拍（场景运行循环内）
> **提示词**：待定（本文先略）

## 做什么

场景运行时的实时调度：读运行实录 + 未命中承重拍 + 上一拍 handoff，决定**下一拍派给谁、戏剧目标是什么**，朝承重拍收敛并判何时收场。顺带做承重拍命中/穿帮快检喂闸。**只给目标不给台词**（schema 焊死）。

## 入参

- [scene-script](../../schema/artifacts/scene-script.md) SceneContract：obligations（承重拍/退出条件/precede 软序）。
- 本场运行实录（紧凑）+ 上一拍 [handoff](../../schema/stores/script-store.md)（Beat.handoff）。
- **轻分辨率**：只本场实录 + 承重拍清单。

## 输出

- [scene-script](../../schema/artifacts/scene-script.md) BeatDispatch：`{owner, dramatic_goal, hits?, directive?}`（瞬态）。
- 收场信号（承重拍全命中 & 退出条件满足，或撞 budget）。

## 交互

- **上游**：[director-setup](./director-setup.md) 合同。
- **下游**：[character](./character.md)（owner 演一拍）→ 回读 handoff 继续循环。
- **快检**：命中/穿帮信号喂 [consistency-gate](../system/consistency-gate.md)。

## 要害

流向权威（收敛承重拍、判收场）；`goal↔plot 对齐`——从角色活跃阶段目标推导本拍戏剧目标，对不上=OOC 预警。
