# 开发路线图（设计 → 可运行系统）

> 从当前状态（设计/schema 齐备、零代码）到成品的里程碑地图。**核心判断：步数是幌子，不确定性才是成本**——真正吃时间的是少数"设计不出来、只能跑出来"的节点。走骨架优先、垂直切片先行，尽早验证最大风险。

---

## 六个里程碑（依赖驱动）

| # | 里程碑 | 干什么 | 关键产出 | 风险 |
|---|--------|--------|---------|------|
| **M0 ✅** | 地基脚手架 | Python 包结构（primitives/schemas/stores/llm/nodes/orchestrator/telemetry）、原语代码化（id / EvidenceSpan / StoryTime / 枚举）、Store 抽象层（JSON + as-of）、LLM 客户端封装（结构化输出 + 重试 + 成本记账）、telemetry 留痕、Orchestrator 骨架 | 能跑空流程（27 UT 全绿） | 低 |
| **M1 ✅** | 确定性内核（无 LLM） | Applier（beat 定序 + 软失效 + arc 状态机）/ Hard-Check（evidence 可解析 / 修为单调 / secret 边界）/ Retriever（规则版 filter→rank→budget，BM25+tiktoken）/ Chunker + Temporal mixin + **Genesis Gate 闭包检查** + 确定性 UT 批 | 46 UT 全绿；检索质量+修为单调标杆落地 | 低 |
| **M2 ✅** | 单章垂直切片 | 创世最小版（seed→L0/L1→Gate→S₀）→ Planner→Director→Character→Script→Writer→Extractor→Faithfulness→Reconciler→Applier；L2 卷脊骨+事件链；walk / `auto` 批跑 | **端到端连出第 1、2 章**（假 LLM UT + 真跑；第 2 章验对账）；真跑可连多章（Writer 可跳过） | 中 |
| **M3 ✅** | 递推闭环 | Assembler 节点画像+Retriever 预算；StagedScriptView；逐拍/场级硬检 + Continuity Critic；Consistency Gate 升级阶梯（过闸才入库）；walk 检查点/rollback/continue；节点 LLM 分层（flash+关推理）+ 本地 reader | **连跑 N 章不崩**（闸接上；批跑可接续） | 高 |
| **M4 ✅** | 长程/规划 | Summarizer 多分辨率摘要、Embedder+向量（JSONL）、Replanner 卷复盘+漂移度量、伏笔全生命周期、re-tiering、WorldOp 落库 | **跑到卷级/百章** | 最高 |
| **M5** | 评估 harness | **M5a ✅** 离线 scorecard（E/D2/C2 + compare CLI）→ 其余 🟢（A3/C4/B3/C1）→ 🟡阈值+judge → 🔴金标/探针（D1）→ 回归 CI | 尺子上线 | 中 |
| **M6** | 打磨产品化 | 多模型分层选型（大模型规划/小模型 dispatch）、成本优化/缓存、跑完"遮天规模"整本、(未来)VLM/MediaStore | 成品 | 中 |

**≈ 30-35 个具体步骤**（每里程碑 4-7 步）。

---

## M2 技术选型（已定）

| 项 | 决定 |
|----|------|
| 模型 | `deepseek-v4-pro`（全节点默认；per-node 可覆盖） |
| 接入 | OpenAI 兼容端点 + `openai` SDK |
| 结构化输出 | instructor（`Mode.JSON`）+ 服务端 `json_object`；配置与密钥一律走 `STORY_*` env（见 `.env.example`） |
| 编排 / 检索 / 存储 | 裸 Python orchestrator；M1 BM25 Retriever；JSON Store（均不升级） |
| Reconciler | **纳入**（管线完整：Extractor→Faithfulness→Reconciler→Applier）。下游 Applier/schema M1 已就绪，新写三块：对账 LLM 节点、旧条目检索取 `target_id`（M1 Retriever/BM25 按 `scope+type` 拉 top-k → LLM 一次批量定 action；去重键 `(scope,type,归一化text)`）、UT（软失效不删 / REINFORCE 必带 target_id / NOOP 留档） |

instructor 内部自修复重试的中间尝试不单独写 RunRecord（末次 usage 入账）——M2 接受，M5 若要精确 E 记账再改。

---

## 三个诚实判断

1. **步数是幌子，不确定性才是成本**。M2/M3/M4 真正吃时间的是三个"只能跑出来"的东西：
   - **记忆抽取忠不忠实**（Extractor prompt 稳不稳）
   - **检索召不召得回**（per-node 画像 + 预算的实际效果）
   - **漂移度量有没有预测力**（意图 vs 实际相减到底准不准）

   这三个每个都可能反复迭代很久；其余二十几步是相对可估的"体力活"。

2. **别等设计全铺完再动代码**。M4/M5 的很多 schema，一碰 M2/M3 的现实就会改。继续冻未验证的假设 = 给毛坯房做精装修。

3. **最该提前的验证 = 尽早跑通 M2 单章切片**（LLM 用糙 prompt、Store 用 JSON 也行）。它一通，上面三个高风险假设第一次被真实数据检验；它不通，后面设计都可能白冻。

---

## 近三步

1. ~~**M0 最小骨架**~~ ✅
2. ~~**M1 Genesis Gate + 确定性 UT**~~ ✅
3. ~~**M2 最细一条线**~~ ✅：`seed → 创世 → 第 1、2 章`（含 Reconciler）；walk / `auto --chapters N` 可批跑。
4. ~~**M3 递推闭环**~~ ✅：Assembler + 一致性闸全链 + staged 过闸入库；walk `rollback`/`continue`；`python -m story_engine.llm` 查节点配置。
5. ~~**M4 长程/规划**~~ ✅：Summarizer/SummaryStore；WorldOp+TierNom 落库；Embedder（fake/openai）+ 语义检索；Replanner 卷复盘；伏笔 due/overdue；Gate `escalate_volume`；walk 卷末 hook。
6. ~~**M5a 离线 scorecard**~~ ✅：`python -m story_engine.eval report|compare`（E1/E2、D2、C2、script clean/flagged）。
7. **下一步 M5 余量**：其余第一批 🟢、阈值评测集、judge 校准；用 compare 做节点 flash A/B 后再冻 `node_profiles`。

---

## 与现有文档的关系

- 设计/契约权威仍在 [ARCHITECTURE](./ARCHITECTURE.md)、[schema/](./schema/README.md)、[nodes/](./nodes/README.md)、[EVALUATION](./EVALUATION.md)。
- 本路线图只管**建造顺序与风险**，不改任何冻结的 schema。
- **原则**：schema 冻结是"当前最佳假设"，M2/M3 跑出来的现实有权推翻它——届时回改对应 schema 文件并记版本。

---

## 待办回收（挂在各里程碑下）

- ~~**M2**：节点真 LLM prompt + orchestrator 接线（含 Reconciler）~~ ✅。
- ~~**M3**：Assembler 画像+预算；一致性闸（硬检两检点 + Critic + 升级阶梯）；staged 过闸入库；walk 检查点接续；高频节点 flash+关推理~~ ✅。dispatch 快检归入硬检；**dispatch 小模型选型**移交 M6（`node_profiles` 已起）。
- ~~**M4**：卷复盘漂移 + L2/L1 判据；summary；world 晋升；分桶重对齐；Embedder；WorldOp；escalate_volume~~ ✅。
- **M5**：GenesisGap / Genesis Gate UT ✅；**M5a 离线 CLI** ✅；其余 🟢（A3/C4/B3/C1）；LLM-judge 校准金标集；E 记账是否计入 instructor 内部重试。
- **M6**：多模型分层打磨（规划 thinking、Critic 严重度标定）；成本优化/缓存；遮天规模整本。
- **M0**：Python 模块划分定稿；~~LLM provider~~ ✅（DeepSeek + instructor，env 配置）；~~embedding~~ ✅（M4）；（未来）VLM 仍挂。
