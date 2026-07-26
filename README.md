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
- [docs/ROADMAP.md](docs/ROADMAP.md) —— 里程碑与建造顺序。

## 状态

**M0 ✅ + M1 ✅ + M2 ✅ 已落地**（见 [docs/ROADMAP.md](docs/ROADMAP.md)）：
原语 / schema / JSON Store / telemetry / Genesis Gate / Applier / Hard-Check /
Retriever（BM25）/ Chunker / Temporal；LLM（DeepSeek + instructor）；
创世 → Planner → Director → Character → Script → Writer → Extractor →
Faithfulness → Reconciler → Applier。走查：`uv run python scripts/walk.py` /
`auto --chapters N`（可跳过 Writer）。`pytest` 全绿。
**下一步：M3 递推闭环**（真检索装配、一致性闸、升级阶梯）。

## 开发

```bash
uv venv
uv pip install -e ".[dev]"          # UT
uv pip install -e ".[openai,dev]"   # 真 LLM（DeepSeek 等）
uv run pytest                       # 全绿（默认 mock，不打网）
```

### 模型配置（走 env）

复制 [`.env.example`](.env.example) 为 `.env`，填 key 即可。常用变量：

| 变量 | 默认 | 说明 |
|------|------|------|
| `STORY_LLM_PROVIDER` | `mock` | `mock` \| `openai`（OpenAI 兼容端点） |
| `STORY_LLM_MODEL` | `deepseek-v4-pro` | 默认模型 |
| `STORY_OPENAI_API_KEY` | — | API key |
| `STORY_OPENAI_BASE_URL` | `https://api.deepseek.com` | 兼容端点 |
| `STORY_LLM_MAX_RETRIES` | `2` | 结构化输出重试次数 |
| `STORY_LLM_NODE_MODELS` | `{}` | JSON，如 `{"writer":"kimi-k3"}` |

真端点冒烟（不进 pytest）：

```bash
# .env 里 STORY_LLM_PROVIDER=openai + STORY_OPENAI_API_KEY=...
uv run python scripts/llm_smoke.py
```

包结构与 `docs/` 一一对应：`primitives ↔ schema/primitives`、`schemas ↔ schema/stores+artifacts`、`nodes ↔ docs/nodes`。
