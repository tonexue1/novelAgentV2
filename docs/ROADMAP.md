# 开发路线图（设计 → 可运行系统）

> 从当前状态（设计/schema 齐备、零代码）到成品的里程碑地图。**核心判断：步数是幌子，不确定性才是成本**——真正吃时间的是少数"设计不出来、只能跑出来"的节点。走骨架优先、垂直切片先行，尽早验证最大风险。

---

## 六个里程碑（依赖驱动）

| # | 里程碑 | 干什么 | 关键产出 | 风险 |
|---|--------|--------|---------|------|
| **M0 ✅** | 地基脚手架 | Python 包结构（primitives/schemas/stores/llm/nodes/orchestrator/telemetry）、原语代码化（id / EvidenceSpan / StoryTime / 枚举）、Store 抽象层（JSON + as-of）、LLM 客户端封装（结构化输出 + 重试 + 成本记账）、telemetry 留痕、Orchestrator 骨架 | 能跑空流程（27 UT 全绿） | 低 |
| **M1 ✅** | 确定性内核（无 LLM） | Applier（beat 定序 + 软失效 + arc 状态机）/ Hard-Check（evidence 可解析 / 修为单调 / secret 边界）/ Retriever（规则版 filter→rank→budget，BM25+tiktoken）/ Chunker + Temporal mixin + **Genesis Gate 闭包检查** + 确定性 UT 批 | 46 UT 全绿；检索质量+修为单调标杆落地 | 低 |
| **M2** | 单章垂直切片 | 创世最小版（seed→L0/L1→Gate→S₀）→ Planner→Director→Character→Script→Writer→Extractor→Applier | **端到端出第 1 章** | 中 |
| **M3** | 递推闭环 | 真检索（画像+预算）、Character 逐拍 dispatch（定锚不定序+handoff）、一致性闸全链（升级阶梯+重试）、Faithfulness Check | **连跑 N 章不崩** | 高 |
| **M4** | 长程/规划 | Summarizer 多分辨率摘要、Embedder+向量库、Replanner 卷复盘+漂移度量、伏笔状态机全生命周期、re-tiering/晋升、rolling horizon | **跑到卷级/百章** | 最高 |
| **M5** | 评估 harness | E 记账 → 🟢第一批指标（C2/D2/A3/C4/B3）→ 🟡阈值评测集+judge 校准 → 🔴金标/合成探针（D1）→ 回归 CI | 尺子上线 | 中 |
| **M6** | 打磨产品化 | 多模型分层选型（大模型规划/小模型 dispatch）、成本优化/缓存、跑完"遮天规模"整本、(未来)VLM/MediaStore | 成品 | 中 |

**≈ 30-35 个具体步骤**（每里程碑 4-7 步）。

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

## 近三步（把"总步数"换成"能立刻验证最大风险的最短路径"）

1. **M0 最小骨架**：包结构 + 原语代码化 + JSON Store + LLM 封装（结构化输出 + 记账）。
2. **M1 Genesis Gate 闭包检查 + 第一条真 pytest**（`check_closure(l1, world) -> GenesisGap`，把"确定性 UT"这条路走实）。
3. **M2 最细一条线**：`seed → 第 1 章散文`，LLM 全用糙 prompt，只求端到端跑通。

跑通这三步，对"系统能不能成"的把握，超过再冻 20 个 schema。

---

## 与现有文档的关系

- 设计/契约权威仍在 [ARCHITECTURE](./ARCHITECTURE.md)、[schema/](./schema/README.md)、[nodes/](./nodes/README.md)、[EVALUATION](./EVALUATION.md)。
- 本路线图只管**建造顺序与风险**，不改任何冻结的 schema。
- **原则**：schema 冻结是"当前最佳假设"，M2/M3 跑出来的现实有权推翻它——届时回改对应 schema 文件并记版本。

---

## 待办回收（挂在各里程碑下）

- **M3**：Character 逐拍 turn 编排与同角色上下文缓存；dispatch 小模型选型与快检规则；各级硬检规则清单 + 重试预算。
- **M4**：卷复盘漂移度量阈值 + "L2 修正 vs L1 修订"触发判据；summary 构建时机与工作缓冲编排；world entity minor→晋升触发信号（复现/跨场景/salience 超阈）。
- **M5**：GenesisGap 清单 schema（创世 Gate 失败载体）；Genesis Gate UT 实装；LLM-judge 校准金标集。
- **M0**：Python 模块划分定稿；技术栈选型（向量库 / embedding / LLM provider / 未来 VLM）。
