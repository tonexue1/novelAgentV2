# WorldStore（世界圣经 / canon）

> **权威源**：本文件。ARCHITECTURE §11.4 留索引指针。
> **类型**：Store（canon：定义域慢变版本化 + 演化域 as-of 软失效）
> **ID 前缀**：`concept.` / `art.` / `loc.` / `org.` / `item.` / `race.`（→ [ids](../primitives/ids.md)）

## 摘要

系统的**设定底座 + 合规尺子**，专治概念漂移。核心哲学：**小核心 + 大长尾**——只种少量承重 canon（core/major），海量细节（minor）由生产层现场造、Recorder 登记、需要才晋升。与 [memory-store](./memory-store.md) 同构（有界画像 + 无界长尾），复用 as-of / 软失效 / evidence 机制。

**类型目录**：`concept.`设定概念(境界体系/源气/道则) · `art.`功法/神通/秘术 · `loc.`地理 · `org.`势力 · `item.`物件 · `race.`种族。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化·核心 canon | Worldbuilder ⇄ Architect 协同 | 创世 | 种子→L0→ Worldbuilder 造 canon ⇄ Architect 写 L1 互引 →L2 |
| 修改·长尾登记 | Director·setup / Character 现场造 → Recorder | 章末 | 默认 minor + 提名晋升 |
| 修改·演化 state | Recorder | 章末 as-of | 势力覆灭、据点易主，软失效不删 |
| 晋升补定义 | Replanner 确认 → Worldbuilder | 卷末 | minor→major/core，补权威 definition |

## 消费（谁读）

各读各切片；core 常驻 + major/minor 选择性；Character 读的过 POV。

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Director·setup（重） | loc+地理关系、在场 org、相关 art/concept/item | 搭场景 canon 底座 |
| Critic + Hard-Check（重） | 术语用法 vs definition、org 关系、地理、境界 ladder | canon 执法 |
| Character | 自己会的 art、所属 org、相关规则（POV 过滤） | 演戏合规 |
| Planner | 活跃势力/地理 | 情节决策 |
| 消费层 Writer/VLM | 全切片 | 渲染保真 |

## 字段

```
WorldEntity:
  id            : concept.{slug} | art.{slug} | loc.{slug} | org.{slug} | item.{slug} | race.{slug}
  canonical_name: str
  aliases       : str[]                    # 别名/旧称/尊号（防同物异名漂移）
  kind          : concept | art | location | faction | item | race
  tier          : core | major | minor
  origin        : seeded | emergent
  # —— 定义域（作者/晋升写；改=显式 retcon，版本化）——
  definition    : str                      # core/major 权威；minor 轻量自动抽取
  attributes    : {k: v}                    # 结构化属性（如 concept.cultivation.ladder 有序列表）
  relations     : {type, target_id}[]       # 包含/相邻/从属/敌对/依赖…
  # —— 演化域（剧情写，as-of，Recorder 更新，软失效不删）——
  state         : {k: v}
  t_valid / t_invalid : chapter            # → common（as-of 主时钟）
  evidence      : EvidenceSpan[]           # → common
  # —— 元 ——
  version       : int
  status        : active | retconned
  established_ch: chapter
```

### tier 分级（决定写多少 / 注不注入 / 校不校验）

| tier | 谁写 | definition | 上下文 | 校验 |
|------|------|-----------|--------|------|
| **core** | Worldbuilder 种 / Replanner 晋升 | 权威 | 常驻 glossary | 用法硬校验 |
| **major** | Worldbuilder / 晋升 | 权威 | 按需检索(involves/loc/语义) | Critic 软校验 |
| **minor** | 生产层现场造、Recorder 登记 | 轻量自动 | 基本不进 | 不硬校验 |

## 三根防漂移支柱 / 不变式

1. 权威 `definition` 唯一 + 涉及即注入（LLM 只读不重编）。
2. `state` as-of 演化可回溯（软失效不删）。
3. Critic 查用法违背 + `aliases` 归一。专用硬检：`attributes.ladder`→境界单调、`relations`(包含/相邻)→位置连续性。
4. 单实体内定义域 + 演化域二分；地理图包含层级强制、相邻/通行代价可选；涌现 minor 自动登记、core/major 需确认晋升。

## 交叉引用

- **写入增量**：[recorder-output](../artifacts/recorder-output.md) 的 `world_ops`。
- **被引用**：[script-store](./script-store.md) 的 `Scene.location`；[arc-store](./arc-store.md)、[memory-store](./memory-store.md) 的 `involves`。
- **配套**：[plan-store](./plan-store.md)（境界阶梯 canon）。
