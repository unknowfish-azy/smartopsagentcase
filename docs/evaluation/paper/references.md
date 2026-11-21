# 参考文献与核实状态（short paper · 标签—探针循环）

> 生成：2026-11-21。**核实标记**：
> - ✅ = 本次检索直接见到原始论文页面/编号/书目信息，可引用。
> - ⚠️ = 仅见二手转述（博客/聚合站），**引用前须核对原文**。
> - 🔍 = 经典文献，出处由领域共识给出，**须核对具体版本与页码**。

---

## A. AIOps / SRE 智能体基准

| # | 文献 | 出处 | 状态 |
|---|---|---|---|
| A1 | Shetty, Chen, Somashekar, Ma, Simmhan, Zhang, Mace, Vandevoorde, Las-Casas, Gupta, Nath, Bansal, Rajmohan. *Building AI Agents for Autonomous Clouds: Challenges and Design Principles.* | SoCC'24. DOI `10.1145/3698038.3698525` | ✅ |
| A2 | Chen, Shetty, Somashekar, Ma, Simmhan, Mace, Bansal, Wang, Rajmohan. *AIOpsLab: A Holistic Framework to Evaluate AI Agents for Enabling Autonomous Clouds.* | arXiv（AIOpsLab 官方项目页给出的 BibTeX） | ✅ |
| A3 | Jha, Arora, Watanabe, …, Puri. *ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks.* | ICML 2025（Oral）。OpenReview `jP59rz1bZk` | ✅ |
| A4 | Wang, Yu, Huang, Huang, Wang, Chen, Lyu. *Cloud-OpsBench: A Reproducible Benchmark for Agentic Root Cause Analysis in Cloud Systems.* | arXiv:2603.00468 [cs.SE]（CUHK / 中山大学） | ✅ |
| A5 | IBM Research × Artificial Analysis. *ITBench-AA*：59 个 SRE 任务，所有受评模型得分 < 50%。 | ITBench 仓库 README 公告（2026-05-27） | ✅（项目公告，非论文） |
| A6 | OpenRCA 2.0：500 个标注事件、11 个前沿模型；命中最少一个根因服务 76.0%，精确恢复完整根因集合仅 20.7%。 | 仅见二手转述 | ⚠️ |

**与本文的关系**：A1–A4 代表「用真实/半真实环境 + 故障注入」的路线，其标签来自**环境终态**而非探针期望，因此不受本文所述循环影响——这正说明循环不是「合成」的必然属性，而是**特定构造方式**的产物（§6.1 的 scope 限定来源）。
A4 的「结果准确率掩盖调查不完整」（JRA 0.78 而 ECR 0.38）与本文 §3.4 的「指标对样本量不敏感」是同类病征的不同表现：**两者都说明结果型指标不足以度量过程**，但 A4 的解法是引入证据闭合率，本文的解法是先审计指标本身是否成立。

## B. 假成功 / 完成度误报的检测

| # | 文献 | 出处 | 状态 |
|---|---|---|---|
| B1 | *From Confident Closing to Silent Failure: Characterizing False Success in LLM Agents.* | arXiv:2606.09863（tau2-bench 排行榜 9,876 条轨迹，8 个模型族） | ✅ |
| B2 | Cao, Driouich, Thomas. *Beyond Task Completion: Revealing Corrupt Success in LLM Agents through Procedure-Aware Evaluation.* | arXiv:2603.03116（τ-bench，27–78% 报告成功为 corrupt success） | ✅ |
| B3 | OverclaimBench：CLI 编码智能体跳过被要求审查的文件比例 67.9%，其中 80.4% 误导用户。 | 仅见二手转述 | ⚠️ |

**与本文的关系**：B1/B2 把「假成功」当作**智能体行为**来检测（轨迹级、judge 级），并指出 LLM-as-judge 会被自信措辞系统性误导（B1）。本文的切入点更早：**在评测集构造阶段**标签就已经被探针期望决定，此时任何 judge（人或模型）都无从判断，因为标签本身不含独立信息。B2 的 corrupt success 定义是「reward=1 但违反程序完整性」，与本文的 false success（reward=0 却被宣称成功）**互补且不相交**；B2 也独立报告了「基准自身的结构性缺陷」（任务范围缺口、奖励信号矛盾、模拟器伪影），与本文 §1.4 的「构造层问题」判断一致。

## C. 基准效度审计与构造依赖

| # | 文献 | 出处 | 状态 |
|---|---|---|---|
| C1 | *Where Does Hindsight Enter Clinical Agent Benchmarks? An Audit of Simulators and Case Construction*（HindAudit）. | arXiv:2611.22241 | ✅ |
| C2 | *Metadata Predictability Is Not Evidence Dependence: An Intervention-Based Audit for Weak-Label Benchmarks.* | arXiv:2605.23701；ICML 2026 Workshop on Hypothesis Testing | ✅ |
| C3 | *When the Label Ignores the Request: Auditing Policy-Selected Targets in Synthetic Conversational Music Recommendation.* | ACM（RecSys 系列，DOI `10.1145/3842413.3842427`） | ✅ |
| C4 | Gururangan et al., *Annotation Artifacts in Natural Language Inference Data.* | TACL 2018 | 🔍 |
| C5 | Poliak et al., *Hypothesis Only Baselines in Natural Language Inference.* | EMNLP 2018 | 🔍 |
| C6 | McCoy et al., *Right for the Wrong Reason: Diagnosing Syntactic Heuristics in Natural Language Inference.* | ACL 2019 | 🔍 |
| C7 | Geirhos et al., *Shortcut Learning in Deep Neural Networks.* | Nature Machine Intelligence 2020 | 🔍 |
| C8 | Sainz et al., *NLP Evaluation in Trouble: On the Need to Measure LLM Data Contamination for Each Benchmark.* | NeurIPS 2023（Findings） | 🔍 |
| C9 | Golchin & Surdeanu, *Time Travel in LLMs: Tracing Data Contamination in Large Language Models.* | ICLR 2024 | 🔍 |

**与本文的关系**（本文定位的关键）：
- **C1 与本文最同构**：它把临床 agent 基准的效度威胁定位在**病例构造**（case construction）而非模拟器，并设计三通道分离审计。本文把同一思路推广到「标签—探针」通道：当标签由 verifier 输入导出时，威胁同样来自构造而非模型。C1 还给出了两条审计陷阱（占位符掩码会制造新线索；跨分类器比较原始概率会掩盖大效应），与本文 §6.4 的「检测器本身有局限」呼应。
- **C2 提供了本文检测器的上层框架**：它把「元数据可预测性」与「证据依赖」分开，主张两者必须与 reader 强度校准一起报告，并构造了「MPDS 中等但 ΔEvi 为零」的反例，说明**只看可预测性会漏判**。本文的 `single_bit_separable` 属于它所说的「可预测性统计」；反极性对照则更接近「干预统计」的低配版（把探针健康度取反，观察指标是否随之翻转）。**本文可与 C2 的两统计框架对齐表述**，这是后续写作的明确改进点。
- **C3 是同族的标签审计**：它发现合成 CRS 基准中标签可以与可见请求矛盾，且强调「生成期守卫跑在生成器内部、用的是生成器自信的信号」，必须做事后、仅用参与者可见证据的审计。这与本文 §3.3 的「词表与评测集同源」是同一类自信信号问题。
- C4–C9 是「基准可被线索/污染解决」的经典脉络；本文的循环是其中**最极端的一例**：线索不需要从训练数据泄漏，也不需要文本表面线索，它就在标签的定义里。

## D. 合成数据的循环验证

| # | 文献 | 出处 | 状态 |
|---|---|---|---|
| D1 | *A mechanism-guided simulation framework for synthetic tax-risk data: Constraint validation and reproducible benchmarking.* | PLOS ONE. DOI `10.1371/journal.pone.0353137` | ✅ |
| D2 | *The Synthetic Data Trap: When It Helps, When It Lies.*（提出 provenance / overlap / disagreement / invariance 四条审计启发式，并明确把「模型生成标签」称为 circular validation） | 技术博客 | ⚠️ 非学术来源，仅作概念参考 |

**与本文的关系**：D1 明确写出 "Synthetic-only evidence and circularity" 与 "The mechanisms generate both predictors and labels, so high discrimination is an internal property of the simulation"——这与本文 §1.2 的核心主张几乎同义，但 D1 面向**预测特征**（XGBoost 判别力），本文面向**核验指标**（标签 vs 探针）。D1 的审计协议（参数追踪、约束校验、实体级泄漏控制、校准压力测试）可作为本文修复协议（§4）的通用化参照。D2 的 invariance test（对等价输入扰动，指标应稳定）在本文中对应**分割稳定性**（§3.4）——但注意本文得到的结论是「稳定得可疑」，与 D2 期待的方向相反，这个反差值得在正文中点明。

---

## 写作待办

1. ⚠️ 条目（A6、B3）在正文中若引用，须先核对原文；否则删除或改为「有报告称」。
2. C2 的 MPDS / ΔEvi 框架建议与本文 C1 检测器**显式对齐**（把 `single_bit_separable` 归入「可预测性统计」，反极性对照归入「干预统计」），并在 §6.4 承认本文只有「低配版干预」。
3. C1（HindAudit）应在 §8 显著引用，它是本文最直接的学术同构先例，也是「构造层效度审计」这一品类已存在的证据。
4. D1 的 "circularity" 表述可直接引用为「合成数据循环性」的既有用法，避免本文被误读为造新词。
