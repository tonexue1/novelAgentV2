# 节点与数据流（框架总账）

> 冻结 schema 前的框架基线：所有处理节点（LLM / 系统）+ 数据流 + 各节点上下文诉求。
> 供集中拷打。稳定后回填 ARCHITECTURE.md。理论依据见 FOUNDATION.md（受控递推 `x_i=f(R(S_{i-1},P,i))` / `S_i=U(S_{i-1},x_i)`）。

---

## 0. 一句话

生产层 `Planner→Director→Character→Recorder` 产出媒介无关的**剧本 Script**；中间由系统节点做**检索装配（R）**、
**一致性闸（守 f）**、**忠实性校验（守 U）**、**落库**。规划层 P（Architect 创世 + Replanner 卷复盘）当锚防漂移；消费层读 Script 渲染成品。

---

## 1. 节点总账

### 规划层（初始化 / 卷边界触发）


| 节点                    | 类型  | 输入                                             | 输出                                         | 触发    |
| --------------------- | --- | ---------------------------------------------- | ------------------------------------------ | ----- |
| **Architect（总纲师，创世）** | LLM | 人工种子(logline/设定)                               | L0(独占,冻结), L1, L2[卷1]                      | 初始化一次 |
| **Replanner（卷复盘师）**   | LLM | ArcStore实际 + MemoryStore(goal/trait轨迹) vs L1意图 | ①诊断漂移 ②L1进度/修订、L2[下一卷]、volume摘要、loose-ends | 卷边界   |


> **维持拆分（已定）**：两节点共用 L1/L2 输出空间与规划技能，本可合一；但**创世（纯生成）vs 卷复盘（先诊断后带约束修正）心态不同**，拆开各自 prompt/选型独立调优。下文"卷复盘"= Replanner。

### 生产层（每章循环）


| 节点                          | 类型       | 输入                                                                      | 输出                                                        | 粒度     |
| --------------------------- | -------- | ----------------------------------------------------------------------- | --------------------------------------------------------- | ------ |
| **Planner**                 | LLM      | P(L0/L1/L2)+Arc进度+到期伏笔+近章摘要                                             | ChapterPlan(=L3)                                          | 每章     |
| **Director·setup**          | LLM      | ChapterPlan+canon+粗人设+旧场景情境                                             | SceneScript（**场景合同**：舞台+戏剧框架+**承重拍[]**+退出条件，**无预排 turn**） | 每场     |
| **Director·dispatch**（现场调度） | LLM(小/快) | 场景合同+运行实录+未命中承重拍+handoff                                                | 下一拍派工(owner+戏剧目标)/收场信号+承重拍命中&穿帮快检                         | **逐拍** |
| **Character**               | LLM      | 本拍戏剧目标+该 owner 的**单角色**画像+goal+voice例句 + 该场已生成 beats(工作缓冲,POV过滤) + 锚定回调 | **一拍** beat（台词/动作/心理实现段）+ handoff 提示                      | **逐拍** |


> **场景运行循环（已定）**：不预排 turn；setup 出承重拍+退出条件 → dispatch⇄Character 逐拍循环涌现 turn，收敛到承重拍全命中&退出条件满足才收场。内容 100% 归 Character，流向权威归 dispatch，handoff 是强提示。护栏：dispatch 用小模型、schema 焊死"目标非台词"。每拍是最小修复单元。

### 固化层 Recorder（章末，过闸后跑）


| 节点             | 类型  | 输入               | 输出                                                                                     |
| -------------- | --- | ---------------- | -------------------------------------------------------------------------------------- |
| **Extractor**  | LLM | 过闸 ChapterScript | MemoryDelta候选(fact/belief/trait/goal + 伏笔ops + secret) + involves/salience/known_by 标注 |
| **Reconciler** | LLM | Delta候选 + 相关旧记忆  | 写回动作(ADD/REINFORCE/SOFT-INVALIDATE)                                                    |
| **Summarizer** | LLM | ChapterScript    | scene/chapter 摘要（多分辨率层级；volume 摘要由 Replanner 卷末产）                                      |


### 校验层（误差投影）


| 节点                     | 类型     | 职责                                                              |
| ---------------------- | ------ | --------------------------------------------------------------- |
| **Hard-Check**         | 系统     | 每拍/每节点结构性硬检：在世/在场、地点存在、能力≤当前、ref 完整、POV 在场、伏笔 FULFILL 前必有 PLANT |
| **Continuity Critic**  | LLM    | **守 f**：OOC / 穿帮 / 逻辑（每场一道，独立宽检索 + 各角色认知边界）                     |
| **Faithfulness Check** | 系统+LLM | **守 U**：证据蕴含判定拒幻觉（跨度存在=系统硬检，蕴含=LLM）                             |


### 系统层（确定性变换 / 检索 / 编排 / 落库）


| 节点                   | 类型  | 职责                                                  |
| -------------------- | --- | --------------------------------------------------- |
| **Retriever**        | 系统  | 分桶检索：过滤 scope/type/章节窗 + 向量排序 + as-of               |
| **Assembler**        | 系统  | 按节点画像（§3）+ token 预算装配上下文                            |
| **Embedder**         | 系统  | 文本→向量                                               |
| **Chunker**          | 系统  | 章→场景块切分                                             |
| **Applier**          | 系统  | 确定性落库：append 流水、应用 MemoryDelta、更新伏笔/主线 status、写摘要索引 |
| **Consistency Gate** | 系统  | 驱动 硬检 + Critic → 重试 / 升级阶梯 / 放行                     |
| **Orchestrator**     | 系统  | 编排循环、重试、并发、工作缓冲管理                                   |


### 消费层（按需渲染，读 Script）


| 节点              | 类型  | 职责                                    |
| --------------- | --- | ------------------------------------- |
| **Writer（写作器）** | LLM | Script + voice → 散文 → ManuscriptStore |
| **VLM（未来）**     | LLM | Script + 渲染指令 → 视频 → MediaStore       |


---

## 2. 数据流（三相）

```
① 初始化:
   人工种子 → Architect → L0 / L1 ──[人工 review 关卡]──▶ L2[卷1]

② 每章循环（章 N）:
   ┌──────────────────────────────────────────────────────────────────────┐
   │  Assembler ← Retriever（各节点各装各的上下文，token 预算，as-of=N）      │
   └──────────────────────────────────────────────────────────────────────┘
        │
   ┌─── 打回③: 重规划整章 ───────────────────────────────────────────────┐
   ▼                                                                       │
   Planner ─L3─▶ [硬检] ─▶ Director·setup ─SceneScript(合同)─▶ [硬检]       │
                             ▲── 打回②: 重导该场 ──┐                       │
                                              │    │                       │
                                    ┌─────────┴────┴ 逐场：现场调度循环 ─────────────────────────┐
                                    │  dispatch ─(owner+戏剧目标)─▶ Character ─beat+handoff─▶ [硬检] ─▶(工作缓冲)│
                                    │     ▲______ 读实录/未命中承重拍/handoff ______│  ①打回: OOC→只重调该拍  │
                                    │  承重拍全命中 & 退出条件满足(或撞预算) → 收场                              │
                                    │  一场毕: [一致性闸: 硬检+Continuity Critic]                               │
                                    │     未过 ─▶ 违规报告 ─▶ 升级阶梯 ①拍→②场→③章→④卷(Replanner)             │
                                    │            (每级重试 N=2; CORRECT 耗尽→flagged 放行; BLOCK 爬满→挂起+呼人)│
                                    └────────────────── 过闸 ──────────────────────────────────────────────────┘
        │  整章 ChapterScript 过闸
        ▼
   Recorder:  Extractor ─候选─▶ [忠实性校验: 证据蕴含] ─▶ Reconciler(写回动作)  +  Summarizer(摘要)
        │
        ▼
   Applier ──确定性写──▶ ScriptStore(原文) / MemoryStore(Delta) / ArcStore(伏笔·主线) / 摘要索引(Embedder)
        │
        └─▶ 章 N 提交；工作缓冲清空；进入章 N+1

③ 卷边界:
   Replanner(卷复盘) 读 实际(ArcStore/MemoryStore) vs 意图(L1)
     → 度量漂移(主线进度差 / 伏笔逾期 / 角色弧线偏离)
     → 更新 L1 进度 / 结构修订(v+1)[人工关卡] / 生成 L2[下一卷] / volume 摘要 / loose-ends 报告
```

### 场景内「逐拍循环」放大（H=per_character 的最细粒度）

```
for beat in SceneScript.scene.beats:        # Director 已定顺序 + owner + 意图
    ctx = Assembler(owner=beat.owner,        # 只注入该角色画像/goal/voice
                    working_buffer=该场已生成 beats(按 owner 的 POV 过滤),
                    retrieved=关系触发经历 + 锚定回调,
                    budget=token 上限)
    beat.realized = Character(ctx, beat.意图)  # 填台词/动作/心理
    HardCheck(beat)                            # 即时结构硬检
    working_buffer.append(beat)
# 全场毕
Critic(scene_script_fragment)                  # OOC/穿帮/逻辑；未过→阶梯修复
```

---

## 3. 各节点上下文画像（R 按节点装配，非一份通用上下文）


| 节点                    | 在干什么    | 读什么                                                        | 分辨率                   | 要害                    |
| --------------------- | ------- | ---------------------------------------------------------- | --------------------- | --------------------- |
| **Planner**           | 定本章方向   | P(L0/L1/L2)+ArcStore 进度+到期伏笔+最近章摘要                         | **粗**(章/卷摘要)          | 情节层决策，不要 beat 细节      |
| **Director·setup**    | 拆场景定合同  | ChapterPlan+WorldStore 设定+出场角色状态(粗)+相关旧场景情境                | **中**(scene 摘要+canon) | 地点/时间/情境连续、承重拍完备      |
| **Director·dispatch** | 现场派下一拍  | 场景合同(承重拍/退出条件)+本场运行实录(紧凑)+上一拍 handoff                      | **轻**(本场实录+承重拍清单)     | 收敛承重拍、判收场、只给目标不给台词    |
| **Character**         | 演一拍     | 本拍戏剧目标+单角色详细画像(含 goal 栈)+voice 例句+关系触发经历+工作缓冲(POV 过滤)+锚定回调 | **细**(近段原文+详细人设)      | 逐字连续+few-shot 语气+认知边界 |
| **Continuity Critic** | 查错(守 f) | 完成的 Script + 独立宽检索(as-of 人设/canon/证据锚定/潜在冲突事实 + 各角色认知边界)   | 验证广度                  | "这场可能推翻什么 / 他怎么会知道"   |
| **Extractor**         | 抽取入库(U) | 过闸 ChapterScript + 可能被推翻/加强的旧记忆                            | 全章 + 相关旧忆             | 消解对账                  |


**Character 六分量心理**（此刻主观状态）：① 我是谁(画像) ② 我想要什么(goal 栈: drive/阶段/场景意图) ③ 我与在场者关系+掌握其秘密 ④ 我知道/不知道什么(认知边界, POV 过滤) ⑤ 此刻状态(情绪/位置 + 工作缓冲连续) ⑥ 本拍戏剧目标(dispatch 给) + anti-OOC 边界。

---

## 4. 两条铁律

1. **LLM↔系统交替**：LLM 节点之间不传自由文本，只传结构化 artifact；由系统节点（硬检 / 校验 / 装配 / 落库 / 编排）在中间校验后流转。
2. **闭环锚在 Script spine**（FOUNDATION §5.5）：记忆是 Script 的投影(U/D)，上下文是记忆的投影(R)；一切投影落回只追加的 Script。B 守 f、D 守 U，两支都夹住环才稳。

---

## 附：上下文源四类（+world canon）

- **走向桶**（要干什么）：PlanStore L2 + ArcStore 实际状态 → 精确过滤。
- **人设桶**（谁怎么反应）：画像(全取快照) + 经历(选择性: involves∩在场 ∪ 语义, 排序 sim×recency×salience) + voice 例句(语义挑)。
- **流水桶**（过去章别穿帮）：多分辨率摘要层级语义检索 + 证据锚定原文。
- **工作缓冲**（本章进行中，非检索）：本章已生成 beats，顺序带，当前场原文/更早场滚动摘要，按 POV 过滤。

