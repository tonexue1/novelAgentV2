# Continuity Critic（续写评审，B）

> **层**：validation ｜ **类型**：LLM ｜ **触发**：每场 Script 完成后一道
> **提示词**：已接（`story_engine/nodes/validation/continuity_critic.py`）

## 做什么

守 f（生成是否忠于记忆）：管软判断——OOC（违背三观/性格/语气）、穿帮（推翻既有事实/canon）、逻辑/语气。参照前一状态 S_{i-1}。**独立做一次针对性宽检索**（"这场戏可能推翻哪些既有设定？"），兜底生成器因预算漏掉的伏笔。

## 入参

- 产出的整场 Script → [script-store](../../schema/stores/script-store.md)。
- **独立宽检索**：as-of 人设/canon/证据锚定/潜在冲突事实 + 各角色认知边界（[memory-store](../../schema/stores/memory-store.md) / [world-store](../../schema/stores/world-store.md) / [arc-store](../../schema/stores/arc-store.md)）。

## 输出

- 通过 / [violation-log](../../schema/stores/violation-log.md) Violation（check_type=llm；OOC/canon_contradiction/voice/logic；含 suggestion）。空列表 = 过。

## 严重度钳制（代码焊死）

模型常把「少铺垫 / 动机弱」标成 `BLOCK/logic`。入库前强制：

- `logic` / `voice` / `OOC` / 未知 category：**禁止** BLOCK → 降为 CORRECT。
- `canon_contradiction` 标 BLOCK 但 `refs` 为空 → 降为 CORRECT。
- 仅 `canon_contradiction` + 非空 refs 可保留 BLOCK。

走查可用 `walk.py --no-critic` 跳过本节点（场收束仍跑硬检）。

## 交互

- 嵌在 [consistency-gate](../system/consistency-gate.md)，[hard-check](./hard-check.md) 之后每场一次。

## 要害

"这场戏可能推翻什么 / 他怎么会知道"。beat 级 OOC 已被逐拍 hard-check 即时抓（只重调该拍）。
