# Story Engine

面向 AI 长篇小说 / 短剧生成的**记忆与生产系统**（Python 架构级重置）。

## 一句话架构

**生产层** `planner → director → character → recorder` 产出**媒介无关的剧本（Script）**，
并把故事梗概 / 人物三观性格以"软失效 + 章节戳"落库；
**消费层**是一组读剧本的渲染器——现在有写作器出小说，未来加 VLM 出短剧。

剧本是两层之间的唯一契约。真相层（剧本/走向/人物/世界）由生产层写、唯一不可变；
成品层（小说/视频）由消费层写、可重复渲染。

## 第一性原理

本项目本质是**上下文工程 + 记忆工程**：把朴素递推 `s(i)=f(s(i-1))` 改造成
"有界上下文 + 结构化多尺度记忆 + 全局规划锚 + 外部寻址"的**受控递推**。
`R`(检索) 和 `U`(记忆更新) 是全部难点，`f`(LLM) 只是执行器。详见理论基础文档。

## 文档

- [docs/FOUNDATION.md](docs/FOUNDATION.md) —— 理论基础 / 心智模型（受控递推的第一性原理，所有架构决策的根据）。
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) —— 架构设计基线（存储层、数据流、节点划分、剧本 schema、记忆规范、检索规范、设计取舍）。

## 状态

**M0 地基脚手架已落地**（见 [docs/ROADMAP.md](docs/ROADMAP.md)）：原语（id/EvidenceSpan/枚举）、schema 模型、JSON Store（含 as-of）、LLM 封装（结构化输出+成本记账）、telemetry 留痕、Genesis Gate 确定性检查、创世/单章 orchestrator 骨架，`pytest` 全绿。下一步：M1 确定性内核 → M2 单章垂直切片。

## 开发

```bash
python -m uv venv           # 建虚拟环境
python -m uv pip install pydantic pydantic-settings pytest
python -m pytest            # 全绿
```

包结构与 `docs/` 一一对应：`primitives ↔ schema/primitives`、`schemas ↔ schema/stores+artifacts`、`nodes ↔ docs/nodes`。
