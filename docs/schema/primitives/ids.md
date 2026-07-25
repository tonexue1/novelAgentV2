# 寻址原语 / ID 体系

> **权威源**：本文件。ARCHITECTURE §11.0 留索引指针。
> **类型**：Primitive（坐标系）

## 摘要

系统一切引用的地基。id 分三类，勿用同一格式硬套。**统一纪律：id 不可变、显示名可变（`display_name` 是字段）；结构化可读优先。** `chapter` 同时是全局 as-of 主时钟。

## 生产（谁铸）

| id | 谁铸 | 何时 |
|----|------|------|
| volume / chapter | Orchestrator | 卷/章开始（递增） |
| scene | Director·setup | 拆场时 |
| beat | Applier | 落库定序（运行时用临时 id） |
| thread / fs / char（核心） | Architect | L1 创世 |
| world（core/major canon） | Worldbuilder | 创世 / 晋升补定义 |
| emergent fs | Recorder 提名 → Replanner 晋升 | 抽取 / 卷复盘 |
| 新出场角色 / world minor 实体 | Registry（Recorder 注册，默认 minor） | 首次出现 |
| memory entry / violation | Applier / Gate | 写入时 |

## 消费（谁读）

全体节点。id 是跨 store 引用的唯一手段；`EvidenceSpan` 用位置 id 回指主真相。

## 字段

### ① 位置 ID（寻址进 ScriptStore，层级，提交后不可变）

```
saga     sg{k}                篇（仅分组，超长篇用；记 volume 区间）
volume   v{n}                 卷（仅分组，记 chapter 区间）
chapter  c{n}                 全局单调递增 —— ★同时是 as-of 主时钟
scene    c{n}.s{m}            章内编号（Director·setup 拆场时铸）
beat     c{n}.s{m}.b{k}       场内编号（Applier 落库时定序；运行时用临时 id）
```

ScriptStore 只追加、永不重排 → 位置 id 一经提交永久有效。位置 id 即 ScriptStore 主键。

### ② 实体 ID（跨全书持久命名实体，`{type}.{slug}`，slug 铸造时冻结）

```
character  char.{slug}                 e.g. char.zhangsan
thread     th.{slug}                   e.g. th.revenge
foreshadow fs.{slug}                   e.g. fs.jade
secret     sec.{slug}                  （特殊伏笔，共用台账/状态机 → arc-store）
world      concept.{slug} | art.{slug} | loc.{slug} | org.{slug} | item.{slug} | race.{slug}
                                        （art.=功法/神通；concept.=设定概念 → world-store）
```

### ③ 不透明 ID（系统生成，非位置非命名）

```
memory entry  m.{ulid}                  软失效 / goal.parent 引用它，须稳定（→ memory-store）
plan          L0 | L1@v{n} | L2.v{k}@v{n}    L0 单例冻结；L1/L2 版本化（→ plan-store）
violation     vio.{ulid}                （→ violation-log）
```

## 不变式

- id 不可变；显示名走 `display_name`/`canonical_name` 等字段。
- 位置 id 提交后永久有效（只追加、不重排）。
- 实体 slug 铸造时冻结，别名走 `aliases`。
- 生产者先于消费者铸造。

## 交叉引用

- 被 [common](./common.md) 的 `EvidenceSpan` 用作寻址基元。
- 所有 stores/artifacts 的引用字段均指向本文件的 id 规范。
