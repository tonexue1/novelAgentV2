# Seed（创世种子，人工唯一入口）

> **权威源**：本文件。ARCHITECTURE §2.6 留索引指针。
> **类型**：Artifact（人工输入，创世 G0 唯一入口）

## 摘要

创世 flow（§2.6）的**唯一人工输入契约**。使命：用尽量少的必填项，把作者意图压进一个结构化种子，喂 Architect 拔出 L0 立意。遵循"小核心大长尾"——**只填立意级锚，不填设定**；海量世界/人物细节交给 G2 协同循环与运行期长出。必填极简（5 项），其余可选、缺省则系统跑时补。

## 生产（谁写）

| 动作 | 节点 | 时机 | 说明 |
|------|------|------|------|
| 初始化 | 人工 | 创世前（G0） | 作者手填，一本书一份 |
| 修改 | 人工 | G1 立意共创回炉 | Architect 出 L0 候选后，人可回改种子再拔 |

## 消费（谁读）

| 节点 | 取哪部分 | 用途 |
|------|---------|------|
| Architect | 全份 | G1 拔 L0 立意；G2 出 L1 骨架时作意图参照 |
| Worldbuilder | genre/tone/hard_rules | G2 补 canon 时定基调与铁律 |
| Planner（间接） | length_target | rolling horizon 卷/章体量规划 |

## 字段

```
Seed:
  # ── 必填（创世最小锚集）──
  logline             : str            # 一句话主线
  genre               : str[]          # 题材标签，如 [东方玄幻, 热血]
  tone                : str[]          # 基调，如 [悲壮, 爽]
  ending_intent       : str            # 结局方向（往哪收，不是细节）
  protagonist_intent  : str[]          # 主角意图链，如 [变强, 护同伴, 探真相]

  # ── 可选（缺省系统补 / 跑时长）──
  hard_rules          : str[]?         # 世界铁律种子，如 [长生需吞噬]；喂 L0 + WorldStore
  length_target       : {unit: chapter|volume, count: int}?   # 预期体量，喂 rolling horizon
  refs                : str[]?         # 对标作品/风格参考
```

## 边界纪律

- **只填立意级锚，不堆设定**：具体功法/地理/势力/配角属 canon 与 minor，走 G2 协同循环（Architect 点名 → Worldbuilder 补）与运行期涌现，不进 Seed。
- **必填 5 项是创世下限**：Genesis Gate 覆盖判据（§2.6）依赖 `ending_intent` + `protagonist_intent` 检查"核心问题有主线撑"。
- **可回炉**：G1 立意共创中，人若不满 L0 候选，可回改 Seed 重拔（属人工共创触点，非一次性）。

## 交叉引用

- **下游**：L0/L1（[plan-store](../stores/plan-store.md)，Architect 据 Seed 产出）、[world-store](../stores/world-store.md)（hard_rules 种铁律）。
- **流程**：ARCHITECTURE §2.6 创世 flow（G0 摄入 → G1 立意 → G2 协同）。
- **校验**：Genesis Gate 覆盖判据消费 `ending_intent`/`protagonist_intent`（见 EVALUATION §2.3 创世 UT）。
