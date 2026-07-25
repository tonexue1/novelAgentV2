# VLM（视频渲染，未来）

> **层**：consumption ｜ **类型**：复合 flow（LLM+系统）｜ **触发**：按需渲染
> **提示词**：待定（本文先略）
> **状态**：未来项，内部多步 flow 待专门设计，**当前只定外层契约、不冻结**。

## 做什么

把 Script + 渲染指令渲染成视频成品，写入 MediaStore。可重渲染、可多版本。

## 入参（外层契约）

- [script-store](../../schema/stores/script-store.md) Script（含 Scene.mood 供氛围）+ 渲染指令。
- [world-store](../../schema/stores/world-store.md) 视觉 canon。

## 输出

- 视频 → MediaStore（成品层，未冻结）。

## 内部 flow（待展开）

≥ 分镜规划 → 生图/生视频 → 配音 → 合成。

## 要害

镜头提示作为"渲染指令"放消费层，不进 Script 真相层。
