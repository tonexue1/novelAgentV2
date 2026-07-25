# Character（演戏）

> **层**：production ｜ **类型**：LLM ｜ **触发**：逐角色 / 逐拍
> **提示词**：待定（本文先略）

## 做什么

以单角色 POV 演**一拍**：给定本拍戏剧目标，自主产台词/动作/心理，并给 handoff 提示（点名/求应/退场）。内容 100% 自主，受三观/goal/voice 约束防 OOC。每拍是 B 的最小修复单元（OOC → 只重调该拍）。

## 入参（六分量心理）

- ① 画像 + ② goal 栈(drive/阶段/场景意图) + ③ 关系+掌握的秘密 + ④ 认知边界(POV 过滤) + ⑤ 此刻状态+工作缓冲 + ⑥ 本拍戏剧目标(dispatch 给)+anti-OOC 边界。
- 详细画像 + voice 例句 + 关系触发经历 → [memory-store](../../schema/stores/memory-store.md)。
- secret 知情(as-of, POV 过滤) → [arc-store](../../schema/stores/arc-store.md)。
- 自己会的 art/所属 org/相关规则(POV 过滤) → [world-store](../../schema/stores/world-store.md)。
- 该场已生成 beats（工作缓冲，POV 过滤）+ 锚定回调 + BeatDispatch → [scene-script](../../schema/artifacts/scene-script.md)。
- **细分辨率**：近段原文 + 详细人设，[assembler](../system/assembler.md) 装配。

## 输出

- [script-store](../../schema/stores/script-store.md) Beat 实现段（dialogue/action/thought）+ handoff。

## 交互

- **上游**：[director-dispatch](./director-dispatch.md) 派工。
- **下游**：[hard-check](../validation/hard-check.md)（每拍即时）→ handoff 回喂 dispatch。

## 要害

逐字连续 + few-shot 语气 + 认知边界（不能说他不该知道的）。
