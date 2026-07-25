# Story Engine 架构设计（结论落盘）

> 面向 AI 长篇小说 / 短剧生成的记忆与生产系统。Python 架构级重置。
> 本文冻结当前讨论结论，作为后续实现的唯一设计基线。

---

## 0. 核心决策：剧本 = 媒介无关的中间表示（IR）

系统切成两段：**语义生产** 与 **媒介渲染**，中间用 **剧本（Script）** 作为媒介无关的中间表示连接。

```
生产层  ──产出──▶  【剧本 Script】  ──被消费──▶  消费层
(语义:发生了什么)      (IR/契约)         (媒介:怎么呈现)
                                          ├─ 写作器 → 小说成稿
                                          └─ VLM(未来) → 短剧视频
```

**关键纪律**：剧本里只放"戏剧内容"（谁说了什么、做了什么、意图/情绪/冲突），
**绝不含**某一媒介的成品文字或分镜。这样写作器与 VLM 共享同一份真相，剧情永不打架。

**为什么不重复**（character 层 vs 写作器）：
- `character`（生产）定"说什么/做什么"：台词内容、潜台词、动作、情绪（语义）。
- `写作器`（消费）定"怎么呈现"：把台词包进旁白描写、按文风遣词（媒介）。
- `VLM`（消费）也定"怎么呈现"：把台词变成配音 + 画面（媒介）。

---

## 1. 分层存储（数据底座）

| 存储层 | 谁写 | 存什么 | 可变性 | 主键/索引 |
|--------|------|--------|--------|----------|
| **PlanStore（规划/意图）** | Architect（创世）+ Replanner（卷复盘） | 全局锚 P：L0 立意 / L1 全书结构 / L2 卷大纲 | L0 冻结；L1/L2 版本化 | 级别 + 卷 + 版本 |
| **ScriptStore（剧本流水）** | Recorder | 每章/集的剧本（真相底稿） | 只追加，永不改 | 章节号 → 场景 |
| **ArcStore（故事走向/梗概）** | Recorder | 梗概、主线进度、伏笔台账 | 更新 + 留版本 | 线id + 章节 + status |
| **MemoryStore（人物）** | Recorder | 三观/性格/语气/能力 | 追加 + 软失效 | scope + type + 章节窗 |
| **WorldStore（世界圣经/canon）** | Worldbuilder（创世/晋升）+ Recorder（长尾/演化）+ 人工 | 概念/功法/地理/势力/物件/种族（core 种 + minor 涌现） | 定义域慢变版本化；演化域 as-of 软失效 | 实体id（见 §11.4） |
| **ManuscriptStore（成稿）** | Writer | 小说散文 | 可重渲染覆盖 | 章节号 |
| **MediaStore（媒资，未来）** | VLM | 短剧视频/分镜 | 可重渲染 | 章节号 |

**分界线**（三层）：
- **意图层**（前瞻控制信号，慢变、版本化）：PlanStore —— "打算怎么走"。
- **真相层**（生产层写、唯一不可变，回溯记录）：ScriptStore / ArcStore / MemoryStore / WorldStore —— "实际走成什么样"。
- **成品层**（消费层写、可重来、可多版本）：ManuscriptStore / MediaStore。

**意图 vs 实际 = 漂移信号**：PlanStore(L1 意图) 与 ArcStore/MemoryStore(实际) 之差，就是漂移量，
由卷边界卷复盘（Replanner）度量并投影回去（见第 2.5 节）。这是防漂移的宏观闭环，不能把 P 塞进 ArcStore，
否则意图与实际相减的能力就没了。

**流水是主真相，Memory/Arc 是派生投影**：ScriptStore 是 bit 级可复现的主真相（冻结、过 B 闸）；
MemoryStore/ArcStore 由有损、非确定性的抽取产出，是主真相的**加速索引而非独立真相**，每条挂 evidence
可回溯核验。重建复现的是"一个"可接受投影而非"同一个"。详见第 3.6 节（D）。

---

## 2. 数据流（一次章节循环）

```
════════════════ 生产层 (Production) ════════════════
PlanStore(P)/ArcStore/World/Memory/Script ─(读)─┐
                                   ▼
   ┌───────────── 打回重做（升级阶梯：④重规划章 ─▶ PLANNER，②重导场 ─▶ DIRECTOR）──────────────┐
   ▼                                                                                              │
   PLANNER ─▶ ChapterPlan ─▶ DIRECTOR·setup ─▶ SceneScript(合同) ─▶ [dispatch⇄CHARACTER 逐拍循环] ─▶ 【剧本 Script】
    (LLM)     └硬检┘             (LLM)         └硬检┘              (LLM小+LLM ①重调拍)             │
                                   ▲(Retriever 系统检索)                                          ▼
                                                    【一致性闸】硬检 + LLM 续写评审
                                                    未过 ──▶ 违规报告，按阶梯重修/升级 ──▶（回上方各节点）
                                                    (CORRECT 耗尽→flagged 放行; BLOCK 爬满→挂起+呼人)
                                                                         │ 过闸
                                                                         ▼
                                                          RECORDER（落库节点）
                                                          ├─ 抽取(LLM)+校验(LLM)
                                                          ├─ 故事梗概/走向 ─▶ ArcStore
                                                          ├─ 人物三观/性格 ─▶ MemoryStore
                                                          └─ 剧本本身      ─▶ ScriptStore
════════════════ 消费层 (Consumption) ════════════════
   【剧本 Script】 + 人物语气(Memory) ─┐
                                       ├─▶ 写作器 WRITER(复合flow) ─▶ 小说成稿 ─▶ ManuscriptStore
                                       └─▶ (未来) VLM 渲染器(复合flow) ─▶ 短剧视频 ─▶ MediaStore
```

- **生产层跑一遍**：产出一集/一章的剧本，Recorder 把"梗概 + 人物变化 + 剧本本身"落库。
- **消费层按需渲染**：拿剧本渲染成小说（现在）或短剧（未来）。消费层可重跑、出多媒介版本，
  不影响生产层真相。

**两相纪律**：生产相只读存储、固化相（Recorder）集中写，避免"边写边改"竞态。

---

## 2.5 规划层 P（全局锚 / 防漂移控制回路）

P 是 FOUNDATION 里那个"慢变控制信号"，打破纯马尔可夫、防止 200 章后跑成另一个故事。
关键是把 P 当**控制回路**而非死大纲：**P（意图，前瞻）** 与 **ArcStore/MemoryStore（实际，回溯）**
之差就是漂移量，由卷边界节点周期性度量并投影回去。

**两个时间尺度的误差投影**（统一视角）：
- **微观**：一致性闸（每场景/每章，防 OOC/穿帮）—— 见后续 B 议题。
- **宏观**：卷复盘 Replanner（每卷，防主线跑偏 / 伏笔逾期 / 角色弧线偏离）。

### 四级 P

| 级 | 是什么 | 谁写 | 何时 | 可变性 |
|----|--------|------|------|--------|
| **L0 立意** | logline / 题材 / 母题 / 基调 / 核心戏剧问题 / 主角弧线意图 / 结局方向 | Architect + 人工种子 | 初始化一次 | **冻结**（改=换书） |
| **L1 全书结构** | 卷划分、主线 threads(起点→目标章 + 转折)、角色弧线终点、全书级大转折、**伏笔总图(埋区间→收区间)**、节奏曲线 | Architect（首版）/ Replanner（修订） | 初始化 + 卷边界 | 版本化，**仅卷边界显式改** |
| **L2 卷大纲** | 本卷目标、本卷派生的埋/收伏笔清单、角色状态目标、粗章级 beat 序列、进退场 | Architect（卷1）/ Replanner（后续卷） | 每卷开头 | 滚动生成，卷边界细化 |
| **L3 章 Plan** | = 现有 ChapterPlan（第 6 节），P 的叶子 | Planner | 每章 | 每章新产 |

> **L3 就是既有的 ChapterPlan**，不新造。A 真正新增的是 L0/L1/L2 三个 artifact + 两个规划节点（Architect 创世 / Replanner 卷复盘）。
> **伏笔 deadline 的来源**：L1 伏笔总图定"某伏笔在第 X 卷收" → L2 派生本卷 due list →
> Planner 每章据此被喂"临期/逾期未收"清单（呼应 C 议题）。

### 两个规划节点（已定：维持拆分）

规划用**两个** LLM 节点。它们共用 L1/L2 的输出空间与部分规划技能，本可合一；但**创世（纯生成）与卷复盘（先诊断、后带约束修正）是足够不同的心态**——拆开后各自 prompt / 选型 / 温度可独立调优，故维持拆分：

- **Architect（总纲师）**[LLM]，初始化一次：人工种子(logline/设定) → 生成 **L0（独占，创立并冻结）** + L1 + L2[卷1]。纯自上而下的创世。
- **Replanner（卷复盘师）**[LLM]，卷边界触发（arc_review 的实体化）。内部两段：
  - **① 漂移诊断**：读实际(Arc/Memory) 对比意图(L1) → 度量漂移（主线进度差 / 伏笔逾期 / 角色弧线偏离，大半可确定性算）。
  - **② 带约束修正**：默认只改下一卷 L2 把剧情拽回；仅当 L1 里程碑不可达 / 出现更优涌现才提 L1 结构性修订(v+1)。附带产 volume 摘要 + loose-ends 报告。
  （下文"卷复盘"即指 Replanner。它是"带历史 + 带诊断"的规划，与 Architect 的"从零创世"共享 L1/L2 编辑机器，但心态不同故独立成节点。）

### 时序

```
初始化:  人工种子 → Architect → L0(冻结) + L1(v1) ──[人工 review 关卡]──▶ L2[卷1]
每章:    Planner 读 L0/L1/L2[当前卷] + 近期梗概/状态 → L3(ChapterPlan) → 下游生产
卷边界:  Replanner(卷复盘) 读 实际(Arc/Memory) vs 意图(L1)
         → 度量漂移(主线进度差 / 伏笔逾期 / 角色偏离)
         → 默认: 只改下一卷 L2 把剧情拽回
         → 仅当 L1 里程碑不可达 / 出现更优涌现: 提 L1 结构性修订(v+1) ──[人工 review 关卡]──▶
```

### 漂移度量（卷复盘算什么）

- **主线进度差**：L1 里程碑应达进度 vs ArcStore 实际进度。
- **伏笔健康度**：L1 伏笔总图到期项 vs ArcStore 已收状态 → 逾期/临期未收清单。
- **角色弧线偏离**：L1 弧线终点 vs MemoryStore trait 曲线现值与趋势（on track / off / 反向）。

### 适应性策略：中庸（已定）

- 默认经**下一卷 L2** 做修正，L1 不动 —— 剧情向 L1 收敛。
- 仅当 L1 里程碑不可达、或出现明显更优涌现走向 → **L1 结构性修订**（版本+1）。
- **人工关卡**只在两处：(a) 初始 L1，(b) L1 结构性修订(v+1)。L2 滚动生成全自动。

### PlanStore schema（叙述版；精确类型已冻结于 §11.2，冲突以 §11.2 为准）

```
L0 (单例, 冻结):
  logline, genre, themes[], tone, target_length, media,
  core_dramatic_question, ending_intent, protagonist_arc_intent[]

L1 (版本化: {version, created_at_ch, status}):
  volumes[]        : {vol_id, title, chapter_range(粗), goal}
  threads[]        : {thread_id, desc, start_ch, target_ch, milestones[{desc, target_vol}]}
  character_arcs[] : {char_id, from, to, key_shifts[]}
  turning_points[] : {desc, target_vol}
  foreshadow_map[] : {fs_id, desc, plant_range, payoff_range, importance}
  pacing_curve     : (可选)

L2 (每卷, 版本化):
  vol_id, version, goal,
  thread_targets[]     : {thread_id, target_milestone}
  foreshadow_due[]     : {fs_id, action: plant|fulfill}
  character_targets[]  : {char_id, target_state}
  chapter_beats[]      : 粗, 每章一句
  entries[], exits[], climax_position

L3 = ChapterPlan (见第 6 节) + derived_from: {l2_vol_id, l1_thread_ids[]}  ← 可追溯
```

---

## 2.6 创世 flow（冷启动 S₀，已定）

递推 `Sᵢ=U(Sᵢ₋₁,xᵢ)` 需要**基例 S₀**。创世 flow = 从人工种子造出"第 1 章可开跑"的初始状态。不是写正文，是把**空状态**填成承重底座。**只建 L1 撑得起来的最小承重集**（小核心大长尾）——海量 minor 设定跑时长出（见 §11.4 与晋升机制）。

**S₀ 产物清单**：

| 产物 | 谁产 | 备注 |
|------|------|------|
| L0(冻结) | Architect | 立意，改=换书 |
| L1(v1) | Architect | 铸 `th./fs./char.` id；防漂移主锚 |
| L2[卷1] | Architect | 详细化首卷 |
| WorldStore(core + L1 点名的 major) | Worldbuilder | 只种承重 canon，minor 留空 |
| ArcStore 初始台账 | Applier(据 L1) | thread→OPEN、foreshadow→PLANNED、secret 建档 |
| MemoryStore(tier0/1 主角 seed 画像) | Architect | origin=seeded，evidence 指种子/L0；龙套不种 |

**分阶段**：

```
G0 种子摄入   人工给 seed(logline/题材/基调/结局方向/主角意图) —— schema 见 schema/artifacts/seed.md
G1 L0 立意    Architect: seed → L0(冻结候选)  ★人工共同敲定 L0(改=换书,必须点头)
G2 协同循环   Architect 出 L1 骨架(点名需要哪些 canon)
             ⇄ Worldbuilder 补 core/major canon(权威 definition)
             ⇄ Architect 回填 L1 引用 → [Genesis Gate 判收敛] → 未闭合再迭代(≤N)
             ★人工可注入创意种子/关键 canon + 回答 Gate 的 open_questions
G3 整包收口   人工审创世包(L0+L1+canon glossary+待决问题) → 批准/逐字段编辑/驳回(带 notes 回 G2)
G4 首卷铺开   Architect: L1 → L2[卷1]
G5 台账/记忆初始化  Applier 据 L1 建 ArcStore；Architect 出 tier0/1 seed 画像(可选)
→ S₀ 就绪，进第 1 章循环
```

**G2 收敛判据（Genesis Gate：系统硬判为主 + 一次 LLM 软复核）**：
- **引用闭包**(硬)：L1 引用的每个 world id 在 WorldStore 存在且 core/major 有权威 definition；L1 自铸 id 自洽。
- **覆盖清单**(硬)：L0 的 `core_dramatic_question`+`ending_intent` 至少被 1 条 main thread 支撑；主角弧线所需力量/世界体系(如境界 ladder)已 seed。
- **无悬挂**(硬)：无 L1 需要却未种的承重 canon；无指向不存在实体的关系。
- **完备性复核**(软，LLM 一次)：能否支撑 L0 立意？产待决问题清单给人工。
- **迭代上界 N=3**：超限把未闭合项 + 待决问题列给人工(G3)，不无限循环。

**方向纪律**：意图驱动 canon（Architect L1 骨架点名 → Worldbuilder 补），不是先堆设定。

**人工共创模型（创世不是"给种子→机器全包→点头验收"，而是人机共创）**：
创世是全书**最高杠杆、最不可逆**的时刻（L0 改=换书），恰恰最该人深度介入。分寸原则——**越贵越不可逆，人介入越深**，正合"小核心大长尾"：人共创核心，机器长尾。创世只发生一次、频率极低，故深度介入不损规模化。

| 决策 | 不可逆性 | 人工角色 | 触点 |
|------|---------|---------|------|
| **L0 立意** | 改=换书 | **共同敲定**（一起拍，不是审） | G1 后 |
| **L1 核心锚**（主线 / tier0-1 / core 伏笔） | 全书主锚 | **共同编辑 + 注入创意种子** | G2 中 |
| **core/major canon** | 慢变 | 审 + 可注入（如"皆字秘"这类临时起意的设定） | G2 中 |
| minor 设定 / 长尾 | 易改 | **不管**，机器跑时长 | — |

三个共创触点（替代原单一 G3 验收）：**G1 后立意共创** → **G2 中骨架共创**（注入创意 + 回答 Gate 的 open_questions，不必等循环跑完）→ **G3 整包收口**（逐字段编辑 / 驳回带 notes 回 G2）。

> 这套人在环机制与运行期一致（卷复盘人工改 L1、违规升级到 human review）：**高杠杆低频 → 深度共创；低杠杆高频 → 机器自主 + 抽样审**。创世是它的一个实例（A-3 人工介入通用模型的种子，另节展开）。

（编排由 [orchestrator](./nodes/system/orchestrator.md) 的创世子流程驱动。）

---

## 3. 生产层四棒

| 节点 | 类型 | 输入 | 产出 | 职责 |
|------|------|------|------|------|
| **Planner** | LLM | PlanStore(L0/L1/L2当前卷)+ArcStore(实际进度/伏笔状态)+近期梗概+世界状态 | ChapterPlan(=L3) | 把 L2 粗大纲落成本章方向：推进哪条主线、埋/收哪些伏笔（含逾期收束）、出场谁、基调 |
| **Director·setup** | LLM | ChapterPlan + 检索(人设/旧剧本/设定) | SceneScript(**场景合同**：舞台+戏剧框架+承重拍+退出条件) | 拆场景、定框架：地点时间、冲突、POV、**本场必须命中的承重拍**与退出条件。**不预排 turn 顺序** |
| **Director·dispatch**（现场调度） | LLM(小/快) | 场景合同 + 运行实录 + 未命中承重拍 + Character 的 handoff 提示 | 下一拍派工(owner+**戏剧目标**) / 收场信号；顺带承重拍命中&穿帮快检 | **临场掌流向**：朝承重拍收敛、判定收场；只给目标不给台词 |
| **Character** | LLM | 该拍 owner 的**单角色**画像+goal+voice例句 + 该场已生成 beats(工作缓冲,POV过滤) + 本拍戏剧目标 | **一拍**(台词/动作/心理) + **handoff 提示**(点名/求应/退场) | **逐角色/逐拍演戏**：受三观/goal 约束防 OOC；内容全自主；OOC 时只重调该拍 |
| **Recorder** | LLM+系统 | 完成的剧本 | 落库(梗概/人物/剧本) | 抽取梗概与人物变化→软失效写回；剧本 append 入库 |

**Recorder 是复合节点**：
- 抽取(LLM)：从**结构化剧本**提取"本章梗概""人物新言行/三观变化"（比在散文成稿上抽取更准更省）。
- **忠实性校验(系统+LLM)**：每个 op 必须被其 evidence 蕴含才放行，反幻觉硬底线（守 U，见第 3.6 节）。
- 校验/消解(LLM)：判断人物变化是否推翻旧记忆 → 软失效 + 章节戳（不删）。
- 落库(系统)：确定性写入三个库。
- 放生产层末尾：固化的是"发生了什么"（语义真相），不是"怎么写的"（媒介成品）。

### 场景运行循环：现场调度 + handoff（已定）

**症结**：若 Director 预排每拍 owner+顺序，Character 退化成填词工，表演被遏死；但全即兴又不保证剧情落地。
**解法**：把"必须发生什么"和"怎么发生"分开——

- **承重拍(obligation beats)**：剧情必须落地的锚（埋/收伏笔、信息揭露、决定、转折），带偏序约束，Director·setup 拥有、**必须命中**。
- **连接戏**：锚间的你来我往，turn 顺序**不预排**，运行时涌现。

**循环**（每场）：

```
setup 出场景合同(承重拍 + 退出条件) →
repeat:
  Director·dispatch 读[运行实录 + 未命中承重拍 + 上一拍 handoff] → 派(owner + 戏剧目标)
  Character(owner) 自主演一拍(台词/动作/心理) + 给 handoff(点名/求应/退场) → [beat 级硬检]
until 承重拍全命中 & 退出条件满足 (或撞预算上限 → 升级)
→ 整场交 Continuity Critic
```

**两条护栏**：① dispatch 用小/快模型（只读紧凑实录+承重拍清单），顺带做"命中/穿帮"快检喂闸；
② schema 焊死 `戏剧目标` 只能是目标不能是台词 —— 从数据契约上禁止 Director 越权写死内容。
**权责**：内容发挥 100% 归 Character；流向权威（收敛承重拍、判收场）归 dispatch；Character 的 handoff 只是**强提示**不是命令。

---

## 3.5 一致性闸与误差投影（微观 / B）

**首要纪律：闸门是真相层的守门人 —— 没过闸的内容不许进 ScriptStore。** 一旦错误被当真相记下，
就成了后续生成的依据、开始逐章复利。这是 FOUNDATION"误差投影/拉回合法流形"的微观落地
（宏观那端是 A 的卷复盘）。

### 两层闸（混合式，已定）

- **确定性硬检**（系统节点，每个生成节点后，近零成本）：在制造错误的那一棒当场拦。可判定项——
  角色在世/在场、地点存在于 WorldStore、能力 ≤ 当前等级(MemoryStore as-of)、引用的
  thread_id/fs_id 存在、伏笔 FULFILL 前必有 PLANT、POV 角色在场。
- **续写评审 Continuity Critic**（LLM，**每场 Script 完成后一道**）：管软判断——OOC（违背三观/性格/语气）、
  穿帮（推翻既有事实/canon）、逻辑/语气。（beat 级硬检每拍即时；因 Character 逐拍生成，beat 级修复=只重调该拍。）
  - **评审独立做一次针对性检索**（"这场戏可能推翻哪些既有设定？"），范围比生成器更宽 →
    生成器因上下文预算漏掉的伏笔由评审兜底（缓解 E）。
  - 参照 **S_{i-1}（前一状态）**，对上递推公式"对着旧状态生成"。

各阶段的检点：Planner 查 PlanStore/ArcStore（死人出场、乱序推进、无视到期伏笔）；
Director 查 WorldStore/ArcStore（地点、时间线、POV 在场）；Character 是重头（OOC/穿帮/能力越级）。

### 严重度分级

| 级别 | 例子 | 处理 |
|------|------|------|
| **BLOCK** | canon 冲突 / 时间线矛盾 / 死人说话 / 能力越级 | 必须解决，**永不静默入库** |
| **CORRECT** | OOC / 语气偏 / 局部逻辑 | 有界重试改进；耗尽则降级 |
| **ADVISORY** | 轻微风格 | 只记录，不重试 |

### 修正 = 升级阶梯（已定）

投影到能吸收错误的最小范围，吸收不了才向上升级——B 的顶端正好接到 A：

```
beat 级补丁 → 场景重导(Director) → 整章重规划(Planner) → 卷复盘(Replanner, =A)
   最小           局部                  本章                   宏观
```

同一根误差投影链，micro↔macro 四级贯通。某条主线反复在闸门失败，本身就是喂给卷复盘的漂移信号。

### 修正循环与降级（已定）

- 违规 → 生成**结构化违规报告** → 带报告在**当前级**重跑（默认预算 N=2/级，可配）→ 仍失败则沿阶梯升级。
- **降级策略**：
  - **CORRECT** 阶梯耗尽 → 接受最优候选 + 标记 `consistency_status=flagged`，流水继续（长时自主跑）。
  - **BLOCK** 爬完整条阶梯（含整章重规划）仍不过 → **挂起该章(blocked) + 呼人**。顺序递推无法跳章，
    canon 崩的章不能当真相记下去 —— 这是唯一必须停下等人的情形。
- **真相层纯度**：过闸入库的章带 `consistency_status`（clean / flagged）。flagged 仍是真相（确实发生了），
  只标着"可能有轻微 OOC"；供人工事后编辑真相层修正。
- 所有闸门结果与重试**留痕**（可观测 + 供 A 复盘）。

### 违规报告 schema

结构化违规 + 升级阶梯全生命周期（`open→fixed/flagged/blocked/advised`），独立 append-only 日志，反复失败喂 Replanner 漂移信号。**精确 schema 见 §11.9**。

---

## 3.6 抽取忠实性与重建（D：Recorder 守 U）

**重构性判断：ScriptStore 是主真相，Memory/Arc 是它的派生投影。** 这解开文档里原本的矛盾——
既说"可随时重建"（当可抛弃索引）又用软失效+章节戳+evidence（当有历史的权威记录）。挑明分工：

- **ScriptStore = 主真相**：冻结、只追加、过 B 闸，bit 级可复现。
- **MemoryStore/ArcStore = 派生投影**：有损、非确定性 LLM 抽取产出，是加速索引**不是独立真相**，
  每条挂 evidence 可回溯核验。**重建复现"一个"可接受投影，不是"同一个"** —— 无妨，因为地面真相永远在 Script。

### B 守 f，D 守 U（对称）

递推两项 `x_i=f(R(...))` / `S_i=U(S_{i-1},x_i)` 各有一个误差投影守卫：

- **B（Continuity Critic）守 f**：生成是否忠于记忆。
- **D（Faithfulness Check）守 U**：记忆是否忠于剧本。

抽取出一条幻觉信念 → 未来 Character 被假人设约束 → 漂移。**抽取忠实性错误是漂移的源头之一**，
D 把它挡在 U 步。两者合起来才夹住递推的两项。

### 机制

1. **证据强制（反幻觉硬底线）**：每个 MemoryDelta / 伏笔 op **必须**引用 Script 具体 scene/beat 跨度作
   evidence；引用跨度不存在 = 系统硬拒。
2. **忠实性校验 Faithfulness Check**（镜像 B，混合式）——**精度为硬底线 + 召回尽力（已定）**：
   - **精度/反幻觉**（系统查跨度存在 + LLM 查蕴含）：每个 op 必须被其 evidence 蕴含；撑不起 → 拒。
   - **召回/防遗漏**：只做轻量 coverage 提醒，不硬卡；漏掉的靠"Script 永在、以后可重抽"兜底。
3. **版本化重建（已定：混合定位）**：
   - 日常：派生层是**有历史的权威记录**——纠错走软失效、不随意重建。
   - 全量重建：**显式版本化维护操作**（升级抽取器），带 `extractor_version` 存每条派生条目，产出新派生版本、
     旧版保留。抽取用**低温/定种**（结构化变换非创作，temp=0 合适）压低非确定性。
4. **去重幂等**：重建按 `(scope, type, 归一化 text)` 合并而非重复插入。
5. **纠错路径**：派生条目事后被评审/人工发现错 → 软失效错的 + 追加对的（都带 evidence）+ 记抽取错误日志。
   **不动 Script。**

---

## 4. 节点 LLM / 系统 划分（索引）

> **节点权威源已拆分到 [`docs/nodes/`](./nodes/README.md)**（每节点一文件：做什么/入参/输出/交互，LLM 提示词暂略）。本节仅留总账索引。

| 层 | 节点（→ 文件） |
|----|---------------|
| **规划层**（初始化/卷边界） | [architect](./nodes/planning/architect.md) · [worldbuilder](./nodes/planning/worldbuilder.md) · [replanner](./nodes/planning/replanner.md) · [planner](./nodes/planning/planner.md) |
| **生产层**（每章循环） | [director-setup](./nodes/production/director-setup.md) · [director-dispatch](./nodes/production/director-dispatch.md) · [character](./nodes/production/character.md) |
| **固化层 Recorder**（章末） | [extractor](./nodes/recorder/extractor.md) · [reconciler](./nodes/recorder/reconciler.md) · [summarizer](./nodes/recorder/summarizer.md) |
| **校验层**（误差投影） | [hard-check](./nodes/validation/hard-check.md) · [continuity-critic](./nodes/validation/continuity-critic.md) · [faithfulness-check](./nodes/validation/faithfulness-check.md) |
| **系统层**（变换/检索/编排/落库） | [retriever](./nodes/system/retriever.md) · [assembler](./nodes/system/assembler.md) · [embedder](./nodes/system/embedder.md) · [chunker](./nodes/system/chunker.md) · [applier](./nodes/system/applier.md) · [consistency-gate](./nodes/system/consistency-gate.md) · [orchestrator](./nodes/system/orchestrator.md) |
| **消费层**（按需渲染，复合 flow，未冻结） | [writer](./nodes/consumption/writer.md) · [vlm](./nodes/consumption/vlm.md) |

> **粒度（已定）**：Character 逐角色/逐拍调用（OOC/voice 最强，内容全自主）；turn 顺序**不预排**，运行时由
> Director·dispatch（朝承重拍收敛、判收场）+ Character 的 handoff 提示涌现；每拍是 B 的最小修复单元
> （OOC → 只重调该拍）。schema 焊死：dispatch 只给"戏剧目标"不给台词。Critic 每场评审一次。

### 数据流（三相）

```
① 初始化:  人工种子 → Architect ⇄ Worldbuilder(造 core/major canon) → L0/L1(引用 world id) ─[人工关卡]─▶ L2[卷1]

② 每章循环:                        ┌───────── 打回③: 整章重规划(BLOCK 爬满) ─────────┐
                                     ▼                                                  │
   Planner ─L3▶[硬检]─▶ Director·setup ─SceneScript(场景合同)▶[硬检]                     │
      ▲(Assembler←Retriever 各装各的上下文)     │            ▲── 打回②: 场景重导 ──┐     │
      │            ┌──────────── 逐场：现场调度循环 ────────────┐                 │     │
      │            │  Director·dispatch ─(owner+戏剧目标)▶ Character ─beat+handoff▶[硬检]─┐│     │
      │            │        ▲______ 读实录/未命中承重拍/handoff ______│           打回①Ↄ (OOC→只重调该拍)
      │            │  承重拍全命中 & 退出条件满足(或撞预算) → 收场              │
      │            └───────────────────────────────────────────┘ 每场完成      │
      │                              [一致性闸: 硬检+Critic] ──未过──▶ 违规报告 → 升级阶梯:
      │                                       │ 过闸                 ①重调拍 →②重导场 →③重规划章 →④卷复盘
      │                                       │            (每级默认重试 N=2；CORRECT 耗尽→flagged 放行；
      │                                       │             BLOCK 爬满→挂起该章 blocked + 呼人)
      │                              Recorder: Extractor→[忠实性校验]→Reconciler + Summarizer
      │                                       │
      │                              Applier ─▶ Script/Memory/Arc/摘要索引
      └────────────────────────────────────┘ (下一章; 缓冲清空)

③ 卷边界:  Replanner(卷复盘) 读 实际(Arc/Memory) vs 意图(L1)   ◀── 阶梯第④级升到这
           → 更新L1进度 / 修订(v+1)[人工关卡] / L2[下一卷] / volume摘要 / loose-ends
```

**LLM↔系统交替原则**：LLM 节点之间不传自由文本，只传结构化 artifact（见第 6 节），
由系统节点（硬检/校验/装配/落库/编排）在中间**校验后流转**。
（命名统一：落库系统节点叫 **Applier**（原 Writer/Applier），**Writer** 只指写作器；ArcUpdater 归入 Applier 的确定性写，模糊判断上移 Reconciler。）

---

## 5. 剧本 Script 结构（系统枢纽）

> **精确类型已冻结于 §11.1**；本节为叙述版，冲突以 §11.1 为准。

媒介无关 IR，既够写作器渲染散文，也够 VLM 渲染画面。

**章级剧本 ChapterScript**
- `chapter/episode 号`、`主题`、`覆盖的主线节点`、`伏笔操作`（埋/收）、`基调`

**场景 Scene[]**，每个场景：
- `场景号`、`地点`、`时间`、`氛围/天气`（← VLM 视觉要用）
- `POV 视角`、`场景目标`、`核心冲突`
- `出场人物 + 各自入场状态/情绪`
- `beat 序列`（**运行时涌现**的实际动作线；turn 顺序不预排，由 Director·dispatch + Character handoff 逐拍产生）

> **SceneScript（合同）≠ Script.Scene（实录）**：Director·setup 出的 SceneScript 只含舞台+戏剧框架+**承重拍**+退出条件，
> 无预排 turn；上面这条 `beat 序列` 是运行时循环产出、落进 **Script**（不是 SceneScript）。

**节拍 Beat[]**，每一拍（派工由 dispatch、内容由 Character）：
- **派工段**（Director·dispatch，运行时）：`owner 角色` · `戏剧目标`（"逼 X 摊牌"级，**禁台词**）· `[命中的承重拍 id?]`
- **实现段**（Character，按类型自主填）：
  - **台词行**：`内容` · `潜台词` · `语气标注`（写作器润色 / VLM 配音要用）
  - **动作/舞台指示**：`做了什么`
  - **心理/情绪**：`内心活动`（写作器转心理描写；VLM 转表情/旁白）
  - **handoff 提示**：`点名某角色 / 求应 / 退场`（喂下一次 dispatch，非最终稿字段）

**刻意不放进剧本**：小说旁白措辞、具体分镜运镜、文风 —— 归各消费层。
（VLM 的镜头提示以后作为"渲染指令"放消费层，不污染剧本。）

---

## 6. 生产层节点间数据契约（artifact）

| Artifact | 产出者 | 关键字段 |
|----------|--------|---------|
| **L0/L1/L2（规划锚 P）** | Architect（创世）/ Replanner（卷复盘） | 见第 2.5 节 PlanStore schema |
| **ChapterPlan（=L3）** | Planner | chapter、theme/tone、chapter_goal、thread_advances[]、foreshadow_ops[]、cast[{required}]+background_hint、story_beats[]、constraints[]、derived_from —— **精确类型见 §11.3** |
| **SceneScript（场景合同）** | Director·setup | scenes[{场景号,目标,地点时间,参与者+入场状态+场级动机[],冲突,POV,**承重拍[{id,描述,owner提示?,偏序约束[],绑定的伏笔/主线op?}]**,退出条件,budget,grounding[]}]；**无预排 turn** —— 精确类型见 §11.5 |
| **BeatDispatch** | Director·dispatch | {owner, 戏剧目标, 命中承重拍id?, directive?}（运行时每拍，禁台词，瞬态）—— 见 §11.5 |
| **Script（剧本）** | Character（逐拍）+ dispatch 派工 | 每拍=派工段(owner+目标)+实现段(台词/动作/心理)+handoff；beat 序列运行时涌现；整章 = ChapterScript（见第 5 节） |
| **RecorderOutput / MemoryDelta** | Recorder(抽取+校验+对账) | 一章原子批：mem_ops[MemOp] + arc_ops + world_ops + tier_noms；MemOp={action, target_id?, type, scope, text, t_valid, evidence(**必填**), strength, involves/salience, extractor_version} —— **精确类型见 §11.6** |
| **SummaryDelta** | Summarizer（章末 scene/chapter）/ Replanner（卷末 volume、篇末 saga） | SummaryEntry[]（多分辨率摘要，建 vec + facet）—— **精确类型见 §11.8** |
| **Violation（违规报告）** | Consistency Gate/Critic | stage, check_type, severity, category, locus, script_evidence + refs, 升级阶梯生命周期(escalation_level/retry/resolution/history) —— **精确类型见 §11.9** |

---

## 7. 记忆条目规范（MemoryStore）

**统一字段**（所有人物相关记忆一种结构，靠字段区分用途）：
- `type`：fact(经历) / belief(三观) / trait(性格) / voice(语气) / ability(能力) / **goal(目标)**
- `scope`：角色 / 线 / 全局（= 命名空间，用于检索过滤）
- `text`：内容
- `vec`：embedding
- `t_valid` / `t_invalid`：章节时间轴（何时成立、何时软失效）
- `strength`：强度/置信（信念、性格程度、执念用）
- `evidence`：出处，指回 ScriptStore 场景块（**必填**，守 U，见第 3.6 节）
- `involves[]`：牵涉实体（角色/物件 id）——**关系触发检索的前提**（经历 fact 用）
- `salience`：显著度（情感/剧情权重，Extractor 打分）——让老而重的记忆不被 recency 淹（经历 fact 用）
- `resolution`：软失效原因，目标/伏笔用（达成 achieved / 放弃 abandoned / 被取代 superseded）
- `status`：伏笔状态机（见第 7.5 节；伏笔台账在 ArcStore，非 MemoryStore）

**画像 vs 经历（语义记忆 / 情节记忆，两种相反的取法）**：

| type | 有界? | 取法 |
|------|------|------|
| trait / ability / goal | 有界 | **全取** as-of 快照 |
| belief | 半有界（累积） | 取活跃；过多按 `strength × 相关性` 挑 |
| voice | profile 有界 + 例句无界 | profile 全取 + 例句语义挑 few-shot |
| **fact（经历）** | **无界（逐章疯长）** | **选择性检索**（见第 8 节人设桶经历子桶） |

**六类的存法**：
- **性格 trait**：对立维度打分（如 慈悲↔狠戾 = -0.8）+ 章节时间线，可画演变曲线。
- **三观 belief**：信念陈述 + 强度 + 证据 + 软失效（世界观/人生观/价值观）。
- **语气 voice**：风格摘要 + **真实台词例句库**（生成靠 few-shot 例句，不靠形容词）。
- **能力 ability**：等级台阶（武功进阶）+ 章节时间线。
- **目标 goal**：多尺度（长期 drive / 阶段目标；场景意图不持久走 SceneScript）+ 层级链接（parent 指向上级目标）
  + 生命周期（追求→达成/放弃/被取代，走软失效 + `resolution`）。长期 drive 的**意图**在 `L1.character_arc`，
  **实际**演变轨迹在此——两者相减 = A 的"角色弧线偏离"漂移度量（第 2.5 节），goal 入库才让那条度量有数据可算。
- **经历 fact**：发生过什么 + `involves[]` + `salience`；蒸馏版，`evidence` 指回原文场景（双分辨率，要逐字才钻取）。

**写回动作集**（Reconciler 决策，替代 mem0 的 DELETE）：
`ADD` / `REINFORCE`(加强度) / `SOFT-INVALIDATE`(设 t_invalid，不删) / `NOOP`
走向专属：`ADVANCE`(推进主线) / `PLANT`·`REINFORCE`·`FULFILL`·`ABANDON`(伏笔状态机，见第 7.5 节)

---

## 7.5 伏笔收束保证（C：台账 + 状态机 + 防悬空）

伏笔 = 长程依赖（FOUNDATION §3），是一阶递推的结构性缺陷，靠显式可寻址台账兜。C 补齐三块：
记录规范、状态机、以及**收束保证（防悬空）**。

### 意图 vs 实际（延续 A 的分离）

- **L1.foreshadow_map（PlanStore，意图）**：计划伏笔总表 `{fs_id, desc, plant_range, payoff_deadline{granularity, ref}, importance}`（见 §11.2；deadline 可粗粒度）。
- **ArcStore 伏笔台账（实际，真相）**：实际埋/收状态与出处。两者之差 = 悬空风险，由卷复盘度量。

**ArcStore 伏笔记录**：伏笔/主线/秘密三类合一张 `ArcRecord`（`kind` 判别，共享状态机），**精确 schema 见 §11.7**。核心字段：`state`（PLANNED→PLANTED→REINFORCED→FULFILLED / ABANDONED）、`importance`、`payoff_deadline{granularity,ref}`、`plant_evidence[]`/`fulfill_evidence`、`abandon_reason`、`history[]`（as-of 回溯）。

### 状态机

```
  PLANNED ──plant──▶ PLANTED ──reinforce*──▶ (PLANTED/REINFORCED)
                         │                          │
                         └──────── fulfill ─────────┴──▶ FULFILLED〔终〕
  任意非终态 ── abandon(显式+理由) ──▶ ABANDONED〔终〕
```

**双驱动，对不上就是漂移信号**：
- **意图**：Planner 的 ChapterPlan 声明本章应 PLANT/FULFILL 哪些（来自 L2 due list）。
- **实际**：Recorder 抽取器从生成剧本检出真的埋/收了什么，带出处更新台账。
- **对账**：计划说已收但抽取显示没真收 → 交 B 的评审（CORRECT 级），不静默记成 FULFILLED。
- 结构守卫由 B 的硬检兜底（FULFILL 前必有 PLANT / ref_integrity）。

### emergent 伏笔（已定：提名 + 晋升）

生产中冒出的非计划埋点：**Recorder 抽取时提名为 emergent 候选 → 卷复盘确认晋升**（正式纳入
台账并回填 L1.foreshadow_map）或忽略。平衡"捕捉有机铺垫"与"台账噪声"。

### 收束保证（正题：防悬空）

- **临期/逾期 surfacing**：Planner 每章拿"临期"（deadline 前 K 章内）+"逾期"（过 deadline 未 FULFILLED）
  清单，被强提示优先收（走向桶已产出，见第 8 节）。
- **逾期升级（按 importance 分级，已定）**——接 A/B 的误差投影阶梯：
  - `minor`：卷复盘自动 reschedule 或 auto-abandon（记理由）。
  - `major`：卷复盘必须显式决策（改期 / 废弃），留痕。
  - `core`：逾期即 **BLOCK 级 → 呼人**。主线/结局级伏笔不许自动漂或废。
- **终局收束保证**：进入**最后一卷前**，卷复盘生成 **loose-ends report** —— 所有非
  FULFILLED/ABANDONED 的伏笔，必须要么排进终卷 L2、要么显式 ABANDON。**没有静默悬空离场。**

### 秘密与认知边界（复用伏笔机制）

**信息不对称 = 戏剧引擎**（戏剧反讽：观众/部分角色知道、当事人不知道）。它和伏笔**同构**：
"信息已存在、对某些角色隐藏、直到某场戏揭晓"——揭晓就是一次状态转移（≈ PLANT→FULFILL）。故复用伏笔台账：

- 高价值不对称信息记为 `kind=secret`（ArcStore，共用伏笔状态机），带 **as-of 单列表 `knowledge[]{char, since_ch}`**（"第 N 章谁知道 X" = `since_ch ≤ N` 集合，`hidden_from` 隐式=补集；见 §11.7）。
- **只对戏剧性关键的秘密显式建模**（80/20）；平凡知识靠 `scope=角色` 的经历近似（谁亲历/被告知谁就知道）。
- **认知边界的两处消费**：Character 装配时按角色 POV 过滤（防"他怎么会知道"）；B 的 Critic 用"全知真相 + 各角色 horizon"查这类穿帮。

---

## 8. 检索规范（Retriever：分桶，不做一次 top-k 打天下）

上下文源分四类（+world canon），并行取，再**按消费节点各自装配**（见第 8.2 节），拼成结构化 prompt：

1. **走向桶**（要干什么）：从 **PlanStore L2[当前卷]** 取本章 beat / 该推进的里程碑 / 本卷 due 伏笔，
   叠加 **ArcStore 实际状态**（已收/未收、逾期）得"临期+逾期未收"清单。
   → **精确过滤**（章节号 + status），不靠向量。
2. **人设桶**（谁怎么反应）：对每个出场角色分两半——
   - **画像（有界，全取）**：`scope=角色` + `type∈{trait,ability,goal,belief}` + `t_valid ≤ N < t_invalid`
     取"第 N 章时点画像快照"（MUST 层）；belief 过多按 `strength×相关性` 挑。
   - **经历（无界，选择性）**：`scope=角色` fact，`过滤(as-of N ∩ (involves∩在场者 ∪ 语义相关本场意图))`
     → `排序(sim × recency衰减 × salience)` → token 预算内 top-k。蒸馏 fact 优先，要逐字才顺 evidence 钻原文。
   - **语气例句**：`type=voice`，语义挑 few-shot。
3. **流水桶**（过去章细节别穿帮）：用本章意图做 query，在 ScriptStore 场景块/摘要做**语义检索**（多分辨率，见 8.1）。
4. **工作缓冲**（本章进行中，非检索）：本章已生成、尚未落库的场景/beat，按顺序全带（MUST）。
   当前场=原文逐拍，本章更早场=滚动摘要；**按 POV 过滤**（角色没在场的场不进其可见缓冲——章内认知边界）。
   与流水桶区别：流水桶=过去章（已落库、靠检索），工作缓冲=本章（编排内存、顺序带）。章末过闸后由 Recorder 落库、缓冲清空。

**原则**：
- 先过滤再排序（先 scope/type/章节窗缩范围，窗内再向量排序）。
- as-of 查询（永远带"当前写到第几章"，闪回取历史态、正常推进取当前态）。
- 精确 vs 语义分开用（走向/伏笔/画像精确过滤；流水/经历语义排序；语义只管情境相似，具体事实靠结构化 fact，已知回调靠 evidence 指针）。
- **认知边界**：给 Character 装配时，人设桶经历 + 工作缓冲都按该角色 POV 过滤（`scope=C` 的经历天然=C 所知）。

### 8.1 检索预算与选取判据（E）

"选多少、选什么"是上下文工程的正题（FOUNDATION §7）。答案不是"每桶给 N tokens"，而是**分级优先**。

**分级 MUST/SHOULD/MAY（不平铺 top-k）**：

| 级 | 内容 | 裁剪规则 |
|----|------|---------|
| **MUST（锚，不可裁剪）** | ChapterPlan beats、到期/逾期伏笔、出场角色 as-of 人设快照、本场相关硬 canon、**活跃伏笔的 evidence 锚定场景** | 预算再紧也不丢 |
| **SHOULD（按判据排序取）** | 语气例句、近场摘要、语义相关旧场景、次要信念 | 预算内择优 |
| **MAY（余量填充）** | 细节色彩 | 有余量才加 |

- **记账单位 = token，预算按节点（已定）**：每节点一个 token 上限（≈ 模型窗口 − 输出留白 − 骨架）。
  MUST 先占用，SHOULD 按 rank 填至预算满，MAY 有余量才加。**副作用**：蒸馏 fact 便宜、原文场景贵，
  按 token 记账**自动偏向"多塞蒸馏、少塞原文"**——多分辨率偏好不用手写规则。
- **MUST 溢出预算 = 场景过载信号** → 升级 Director 拆场景（接 B 的升级阶梯）。
- 各桶形状不同：走向桶几乎全 MUST（控制信号必须完整，不采样掉任一到期伏笔）；人设桶 MUST=画像快照，经历/例句是 SHOULD；**流水桶是最弹性的桶**（噪声/冲淡风险都在此）。

**流水桶长程 = 多分辨率 + 证据锚定（已定）**：
- **MUST：证据锚定**——活跃伏笔的 `plant_evidence` 指针 → 显式寻址拉入对应场景。
  这就是 FOUNDATION §3 的 **skip-connection**：把长程检索从"祈祷语义命中"变成"精确寻址"。E 最难的一侧由 C 解掉。
- **SHOULD：越远越压缩的多分辨率**——维护摘要层级 scene→chapter→volume（对齐 L3/L2/L1）。语义检索命中
  **摘要层**（embed 对象=摘要，低噪、向量少），近段命中原文、远段命中章/卷摘要，需逐字才顺 evidence 钻原文。
  三路召回互补：**情境相似→摘要 embedding；具体事实→结构化 fact；已知回调→evidence 指针**。
  摘要是 Script 的派生投影（有损、evidence=所概括场景、可版本化重建，守 D）。

**自适应预算（已定）：lean-by-default, widen-on-error**：
- 正常一遍用精简预算（省成本、防冲淡）。
- B 的 Continuity Critic 查出穿帮、且事实其实在 ScriptStore 里只是没检索到 → 重生成那一遍**加宽相关桶预算**。
  （评审员本就独立做更宽检索，此为自然延伸。）大多数章便宜跑，难章才花钱。

### 8.2 各节点上下文画像（R 按节点装配，非一份通用上下文）

单章生成里 `f` 不是一个节点——Planner/Director/Character 各是一个 f，各看各的；Critic/Extractor 也各有其上下文。
**R 给每个节点按其活儿装配不同的子集/分辨率/token 预算**：

| 节点 | 在干什么 | 读什么 | 分辨率 | 要害 |
|------|---------|--------|--------|------|
| **Planner** | 定本章方向 | P(L0/L1/L2)+ArcStore 进度+到期伏笔+最近章摘要 | **粗**(章/卷摘要) | 情节层决策，不要 beat 细节 |
| **Director·setup** | 拆场景定合同 | ChapterPlan+WorldStore 设定+出场角色状态(粗)+相关旧场景情境 | **中**(scene 摘要+canon) | 地点/时间/情境连续、承重拍完备 |
| **Director·dispatch** | 现场派下一拍 | 场景合同(承重拍/退出条件)+本场运行实录(紧凑)+上一拍 handoff | **轻**(本场实录+承重拍清单) | 收敛承重拍、判收场、只给目标 |
| **Character** | 演戏(台词/动作) | 本拍戏剧目标+**详细画像**(含 goal 栈)+**voice 例句**+关系触发经历+**工作缓冲**(本章可见,POV 过滤)+锚定回调 | **细**(近段原文+详细人设) | 逐字连续+few-shot 语气+认知边界 |
| **Continuity Critic**(B) | 查错 | 产出 Script+**独立宽检索**(as-of 人设/canon/证据锚定/潜在冲突事实+各角色认知边界) | 验证广度 | "这场戏可能推翻什么/他怎么会知道" |
| **Extractor**(U) | 抽取入库 | 产出 Script+可能被推翻/加强的旧记忆 | 新 script 全文+相关旧忆 | 消解对账 |

**Character 六分量心理**（此刻主观状态）：① 我是谁(画像) ② 我想要什么(goal 栈:drive/阶段/场景意图) ③ 我与在场者关系+掌握其秘密
④ 我知道/不知道什么(认知边界,POV 过滤) ⑤ 此刻状态(情绪/位置+工作缓冲连续) ⑥ 本拍戏剧目标(dispatch 给)+anti-OOC 边界。
**goal↔plot 对齐**：dispatch 从角色活跃阶段目标推导本拍戏剧目标，让他顺着追就自然演出承重拍；对不上 = OOC 预警（B 抓）。

---

## 9. 与 mem0 / Graphiti 的关系（设计取舍）

**从 mem0 保留**：LLM 自动抽取事实、向量语义检索、命名空间隔离。
**改掉 mem0**：冲突时 DELETE → 换成 Graphiti 式**软失效 + 章节戳**；补上原文层（流水）与未来层（走向）；每条记忆挂 as-of 章节。

**Graphiti 核心（借鉴）**：双时态边（事件时间 t_valid/t_invalid + 录入时间 created/expired）、
矛盾时软失效不删、实体去重、混合检索。→ 这正是"人物弧线可回溯、不 OOC"的根基。

---

## 10. 要拍死的原则

1. **剧本是唯一契约**：生产层只产剧本，消费层只吃剧本。加媒介 = 加渲染器，永不动生产层。
2. **真相与成品分离**：记忆/梗概从剧本抽取落库，不从成稿抽——媒介换了真相不变。
3. **软失效不删除**：人物弧线、设定演变全靠它，历史永远可重建。
4. **一切带章节戳 + 出处**：任意时点可 as-of 回溯，可点回原文。
5. **LLM 产出必须结构化**：节点间传 JSON 契约，自然语言只存在于最终成品和例句里。
6. **生产相只读、固化相只写**：集中落库，避免竞态。
7. **消费层可重跑**：改文风、重出视频，随时基于旧剧本重渲染。
8. **闸门守真相**：没过一致性闸不许进 ScriptStore；BLOCK 永不静默入库，误差就近投影、按阶梯升级（见第 3.5 节）。
9. **Script 主真相、派生投影可重建**：Memory/Arc 是 Script 的有损投影，每条挂 evidence；抽取需证据蕴含（守 U），重建版本化（见第 3.6 节）。

---

## 11. Schema 冻结基线（索引）

> **schema 权威源已拆分到 [`docs/schema/`](./schema/)**（单一真相源，防两处漂移）。本节仅留索引指针。
> 以数据流为地图，逐节点冻结 I/O 精确类型。类型记法：`?`=可选，`[]`=数组，`|`=枚举。

| § | 冻结物 | 类型 | 权威文件 |
|---|--------|------|---------|
| 11.0 | 寻址原语 / ID 体系 | Primitive | [primitives/ids](./schema/primitives/ids.md) |
| — | EvidenceSpan / StoryTime / 枚举 | Primitive | [primitives/common](./schema/primitives/common.md) |
| 11.1 | Script（ChapterScript/Scene/Beat） | Store·主真相 | [stores/script-store](./schema/stores/script-store.md) |
| 11.2 | PlanStore（L0/L1/L2） | Store·意图 | [stores/plan-store](./schema/stores/plan-store.md) |
| 11.3 | ChapterPlan（L3） | Artifact | [artifacts/chapter-plan](./schema/artifacts/chapter-plan.md) |
| 11.4 | WorldStore（世界圣经） | Store·canon | [stores/world-store](./schema/stores/world-store.md) |
| 11.5 | SceneScript + BeatDispatch | Artifact | [artifacts/scene-script](./schema/artifacts/scene-script.md) |
| 11.6 | RecorderOutput / MemoryDelta | Artifact | [artifacts/recorder-output](./schema/artifacts/recorder-output.md) |
| 11.7 | ArcStore（伏笔/主线/secret） | Store·派生 | [stores/arc-store](./schema/stores/arc-store.md) |
| 11.8 | SummaryStore（多分辨率摘要） | Store·派生 | [stores/summary-store](./schema/stores/summary-store.md) |
| 11.9 | Violation（违规报告） | Store·日志 | [stores/violation-log](./schema/stores/violation-log.md) |
| §7 | MemoryStore（人物记忆） | Store·派生 | [stores/memory-store](./schema/stores/memory-store.md) |

阅读顺序与不变式速查见 [schema/README](./schema/README.md)。

---

## 附：后续待办（未在本文冻结）

- [x] **规划层 P（A 议题）**：四级 P、Architect(创世) + Replanner(卷复盘) 两节点、意图 vs 实际漂移闭环、中庸适应性 —— 见第 2.5 节。
- [x] **一致性闸 / 微观误差投影（B 议题）**：混合闸、升级阶梯、标记后继续降级 —— 见第 3.5 节。
- [x] **伏笔收束保证（C 议题）**：意图/实际台账、状态机、分级逾期升级、终局 loose-ends —— 见第 7.5 节。
- [x] **抽取忠实性 & 重建（D 议题）**：Script 主真相/派生投影、证据蕴含、版本化重建、B 守 f / D 守 U —— 见第 3.6 节。
- [x] **检索预算（E 议题）**：分级 MUST/SHOULD/MAY、token 按节点预算、证据锚定长程、lean/widen 自适应 —— 见第 8.1 节。
- [x] **记忆/索引层设计**：画像 vs 经历二分、goal 类型、involves/salience、多分辨率摘要层级、embed 摘要、认知边界/秘密、各节点上下文画像 —— 见第 7 / 7.5 / 8 / 8.2 节。
- [x] **节点全景 + 数据流总账**：全节点(LLM/系统)清单、三相数据流、Character per-character 粒度、Critic 每场、命名清理(Applier) —— 见第 4 节。
- [x] **寻址原语 / ID 体系（G 议题，第0步）**：三类 id、evidence 跨度、as-of 主时钟、铸造责任 —— 见第 11.0 节。
- [x] **Script / ChapterScript / Scene / Beat（第1个）** —— 见第 11.1 节。
- [x] **PlanStore L0/L1/L2（第2个）** —— 见第 11.2 节（含 saga 层 / 滚动地平线 / thread 分层，撑 1000+ 章）。
- [x] **ChapterPlan = L3（第3个）** —— 见第 11.3 节（story_beats 命名、cast required/background、章级义务不映射到场）。
- [x] **SceneScript（场景合同）+ BeatDispatch（派工）** —— 见第 11.5 节（定锚不定序、obligation 场景内定位 id、precede 软约束、随 Script 落库、退场硬检兜底）。
- [x] **MemoryDelta / RecorderOutput** —— 见第 11.6 节（一章原子批：mem_ops/arc_ops/world_ops/tier_noms；MemOp 对齐 MemoryStore；secret 走 arc、NOOP 留档、evidence 必填）。
- [x] **ArcStore 台账（伏笔/主线/secret）** —— 见第 11.7 节（ArcRecord 合表 kind 判别、ArcOp、状态机补 thread 线、secret 单列表 knowledge[]、emergent 内联提名）。
- [x] **SummaryStore 摘要索引** —— 见第 11.8 节（多分辨率 scene→chapter→volume→saga、(level,ref) 键、facet + 单 vec、独立 SummaryDelta、纳入 harness 评估）。
- [x] **Violation（违规报告）** —— 见第 11.9 节（升级阶梯全生命周期、独立 append-only 日志、evidence 双指、喂 Replanner 漂移信号）。
- [x] **数据流节点 I/O schema 全闭环**（§11.0~11.9：ID → Script → PlanStore → ChapterPlan → WorldStore → SceneScript/BeatDispatch → MemoryDelta → ArcStore → SummaryStore → Violation）。
- [x] **WorldStore schema（世界圣经，防概念漂移）** —— 见第 11.4 节（WorldEntity 定义域/演化域二分、core/major/minor 分级、Worldbuilder 节点、三根防漂移支柱）。地理关系图的位置连续性硬检规则清单仍待细化（压测遮天时暴露）。
- [ ] 摘要层级的构建时机与运行态工作缓冲的编排细节（Summarizer 章末、Replanner 卷末）。
- [x] **场景运行循环（生产层）**：现场调度(Director·dispatch) + Character handoff，承重拍/退出条件，内容自主、流向可控 —— 见第 3 节"场景运行循环"。
- [ ] Character 逐拍生成的 turn 编排与同角色上下文缓存（per-character 的成本缓解）；dispatch 小模型选型与快检规则。
- [ ] 定卷复盘的漂移度量阈值与"L2 修正 vs L1 修订"的触发判据；定各级硬检规则清单与重试预算。
- [x] **创世 flow / 冷启动 S₀** —— 见第 2.6 节（S₀ 产物清单、G0~G5 阶段、Genesis Gate 收敛判据、意图驱动 canon、人工关卡）。
- [ ] **world entity minor→晋升的触发信号**（与角色 re-tiering 对称）：复现次数 / 跨场景使用 / salience 累积超阈值 → Recorder 提名。当前 §11.4 只说"需要才晋升"，未定判据（皆字秘式"临时起意→用大半本书"的捕捉靠它）。
- [ ] 定 Python 模块划分（stores / nodes / orchestrator / renderers）。
- [ ] 选型：向量库、embedding 模型、LLM provider、（未来）VLM。
