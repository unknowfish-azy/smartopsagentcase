# P2-7 方案 v1：多 Agent 辩论 / 知识图谱+神经符号 / 因果图与反事实

> **缺口出处**：`docs/design/llm-distill-stack/ARCHITECTURE.md` §1.2 三张 P2 行——
> ①「因果 GNN / 反事实 | 未找到 | P2，A@1 增益需消融证明」；
> ②「知识图谱 + 神经符号推理机 | `knowledge/` 有 catalog，无图谱/推理机 | P2」；
> ③「多 Agent 辩论 | `agent/subagents/` 有 log_diagnosis/patrol，无 debate 收敛 | P2」。
>
> **本文件是这三件事的唯一口径**。数字口径沿用 `docs/competition/fact-sheet.md`：**数字必须带 n 与状态**；`NOT_RUN`/`null` 不得写成达标；合成数据结果不得写成生产性能。
>
> **协作模型**：本文档由本智能体产出（方案 / 计划），实现与测试交其他模型执行；工作包可逐项交接。

---

## 0. 结论先行

三件事**共享同一条铁律**：必须有**可机检的对照实验** + **诚实口径**，否则就是炫技——缺口表里对因果 GNN 已经写明「A@1 增益需消融证明」，另两件同理。

**推荐顺序：A 多 Agent 辩论 → B 知识图谱+神经符号 → C 因果图/反事实。**

| 序 | 子项 | 为什么这个顺序 | 对应赛维（AI 技术深度 35%） |
|---|---|---|---|
| ① | **多 Agent 辩论** | 复用度最高（`agent/subagents/` + `AgentExecutor` + `stats_inference` 全部现成）；投入最小、闭环最快；**反例可得**（不收敛就是结论，不是失败） | **Agent 8 分**（多智能体协同） |
| ② | **知识图谱 + 神经符号** | 有 737 条 catalog 作真实语料；符号推理可解释、可回溯；与现有 hybrid 检索做对照 | **RAG 6 分** + 技术 8 分 |
| ③ | **因果图 / 反事实** | 依赖前两件的评测纪律；反事实构造必须先定义判据，设计成本最高 | LLM 8 分 + 创新性 25% 的技术分 |

**三件都不做的选项也写在这里**：若交付周期紧张，只做 ① 即可交代「多智能体协同」，②③ 在材料里如实写 `NOT_RUN` + 计划。**不接受**的是：没做却写「已支持」。

---

## 1. 现状（代码事实，2026-11-22 复核）

| 能力 | 现状 | 证据位置 |
|---|---|---|
| 根因图模型 | **6 个相关式模型**：`heuristic` / `gcn` / `gat` / `graphsage` / `tgat` / `tgpm`；统一签名 `forward(x, edge_index, edge_weight=None)`；PyG 缺失时退化纯 torch 手写 | `ai-service/app/training/graph_model.py`（353 行） |
| 反事实 / do-干预 | **零实现**（全仓 `counterfactual` / `do(` / `intervention` 无命中） | — |
| 消融骨架 | **已就绪且被复用**：4 场景（`static_sev_random` / `dynamic_spread` / `large_graph` / `rootcause_degraded`）× 6 模型，指标 A@1 / A@3 / MRR，固定种子可逐位复现 | `ai-service/scripts/ablation_rootcause.py` |
| 统计推断 | **已就绪**：Wilson / Clopper-Pearson / bootstrap（差值）/ 精确二项 / McNemar / Wilcoxon / 配对·独立置换 / **Holm·BH** / Cohen's h·κ / RR·OR / ICC·DEFF / 样本量反解 | `scripts/stats_inference.py`（48 项单测） |
| 消融统计落地件 | 已跑 **192 runs**（6 模型 × 4 场景 × 8 seeds），含分层 bootstrap CI + 配对 McNemar + 双校正 | `scripts/ablation_rootcause_stats.py`（728 行）→ `reports/ablation-rootcause-stats.*` |
| 知识图谱 | **无实体/关系抽取、无图存储、无推理机**；只有 catalog 摄入 + chunk 检索 | `knowledge/service.py`（`ingest_catalog` / `search`）、`knowledge/retrieval/{bm25,hybrid,vector_store,version_filter}.py` |
| 「知识图谱」易混点 | `docs/design/knowledge-review-graph-v1/` 是**审核台的图视图 UI**（节点=候选/条目/事件），**不是推理图谱**，不得拿它当本缺口已闭环 | 同上 |
| 多 Agent | `SubAgent` 基类只**产出预置 DAG 模板**（`PlanStep` 列表），执行复用 `AgentExecutor`/`DagExecutor`；现有 `log_diagnosis` / `patrol` 两个 | `agent/subagents/{base,log_diagnosis,patrol}.py` |
| 辩论 / 反驳 / 收敛 | **零实现**（无 debate / rebuttal / convergence 关键词） | — |
| 受控评测集 | 144 条受控 verification（带 `ground_truth` + `state_assertions`），但 **M31 已判定主指标存在「标签—探针循环」**，不得直接拿来当能力证据 | `SmartOps-Dataset/Controlled/v1/`；fact-sheet M31 / 口径⑨ |

> **口径提醒**：M31 的循环审计结论对三件事都适用——**凡是「用生成器给的标签」做对照，必须先证明标签不是模型输入的函数**，否则结论只能写「链路自洽性」。

---

## 2. 子项 A：多 Agent 辩论（推荐先做）

### 2.1 目标

同一诊断问题 → **N 个角色各自独立取证并给结论** → **反驳轮**（看到彼此结论后修正）→ **收敛判定**（一致 / 仲裁 / 未收敛），全程留可机检的判据与统计。

### 2.2 非目标

- 不做「无收敛保证的自由多轮聊天」——没有收敛判据的辩论只是串场。
- 不做真·分布式共识（RAFT/PBFT 类，§1.2 已列 P3「不建议在交付周期内碰」）。
- 不替换现有 `AgentExecutor` / DAG 编排（复用，不重建）。

### 2.3 设计

**角色（复用 `SubAgentSpec` 声明，不新建编排框架）**

| 角色 | 可见证据通道 | 工具白名单 | 职责 |
|---|---|---|---|
| `log_diagnosis` | 容器/Nginx/服务日志 | 现有 `tool_names` | 从日志找故障现象与时间点 |
| `metric_inspector` | 指标/告警 | `sentinel.alerts`、`sentinel.metrics` | 从指标越界定位异常面 |
| `topology_inspector` | 调用链/依赖 | `inspector.events` | 从拓扑传播定位候选根因 |
| `change_auditor` | 变更/审计 | `audit.chain` | 关联近期变更 |

> **关键防循环**：每个角色**只能看到自己通道的证据**。若四个角色都读到同一份检索结果，结论一致是**同源自证**，不是辩论生效——这是硬约束，不是建议。

**辩论协议（可机检）**

```
round 0（独立）：每角色产 conclusion_i = {top1, candidates[], evidence[ids], rationale}
round 1（反驳）：每角色看到「他人 top1 集合 + 各自 evidence id」，必须产出
                 rebuttal_i = {agree_with: id | null, dispute: 具体到证据 id 的不同意点,
                               new_evidence: ids, revised_top1}
最多 2 轮；超过即收敛失败
仲裁：judge 角色（或多数 + 证据强度）产出 final
```

**收敛判据（三项都落盘，可机检）**

- `converged`：最后一轮所有角色 `revised_top1` 相同；
- `changed`：至少一个角色在反驳后改了 `top1`（说明反驳真的起了作用，不是摆设）；
- `escalated`：2 轮后仍不一致 → **如实记为未收敛**，不得粉饰成「达成一致」。

**对照实验（必须）**

- 基线：单角色（`log_diagnosis` 单独） vs 四角色辩论；
- 数据：受控集 **n≥32**（四类各 8，与 DS-02 用例对齐），真实知识库检索结果作为证据池；
- 指标：`root_cause_accuracy`、`convergence_rate`、`changed_rate`、`mean_rounds`、`evidence_precision`（最终引用证据中支持 `ground_truth` 的比例）；
- 统计：**配对** McNemar（同题两条件）+ Wilson 区间 + **Holm 校正**；n 与有效 n 同时给（受控集 ICC/DEFF 见 M30，有效 n 可能远低于名义 n）。

### 2.4 工作包

| 包 | 内容 | 产出 |
|---|---|---|
| A1 | `agent/subagents/debate.py`：角色声明 + 辩论协议（round/rebuttal/arbitrate）+ 纯函数判定 `converged/changed/escalated` | 模块 + 单测 |
| A2 | 证据通道隔离：每角色独立 `ToolRegistry` 视图 + 独立证据 id 空间 | 模块 + 单测（防同源） |
| A3 | 评测脚本 `scripts/eval_debate.py`：基线 vs 辩论，n≥32，落 `reports/debate-eval-<tag>.json` | 脚本 + 报告 |
| A4 | 统计收口：McNemar + Wilson + Holm + 有效 n（复用 `stats_inference`） | 报告小节 |
| A5 | 口径登记：fact-sheet 新条目 + 禁止事项 | 登记 |

### 2.5 门禁

| 编号 | 判据 |
|---|---|
| A-G1 | 纯函数单测：收敛/变更/升级三判据正确；反驳后 `top1` 变化被正确识别 |
| A-G2 | **防循环回归**：构造「全角色同一证据池」的负对照，必须被测试判为**无效实验**（返回 `invalid`，不是高分） |
| A-G3 | 对照实验：单角色 vs 辩论，`n` 与有效 `n` 同时给出；**未收敛样本单独计数**，不得从分母剔除 |
| A-G4 | 统计：McNemar + Wilson + Holm 齐全；**Holm 后不显著必须写「未证明增益」** |
| A-G5 | 口径：fact-sheet 写明 `n`、`converged/escalated` 分布、证据通道隔离；**禁止**写「多 Agent 辩论提升准确率 X%」除非 Holm 显著 |

### 2.6 风险

1. **同源循环**：角色共享证据池 → 一致率虚高。缓解：A2 硬隔离 + A-G2 负对照。
2. **LLM 成本/延迟**：真实模型（qwen3:1.7b 实测约 5.4s/次）下 4 角色 × 2 轮 × 32 题 ≈ 128 次调用；需先小 n 试跑估时，超时则降级为「离线脚本 + 缓存结论」。
3. **未收敛被美化**：缓解：A-G3 强制单列 `escalated`。

### 2.7 落地记录（2026-11-22，用户点名「A继续」）

| 包 | 状态 | 产出 |
|---|---|---|
| A1 | ✅ | `agent/subagents/debate.py`（角色声明复用 `SubAgentSpec`、round0/round1/仲裁协议、纯函数 `detect_changes` / `judge_verdict`、`DebateRunner`；推理由可注入 `RoleAgent` 提供） |
| A2 | ✅ | `agent/subagents/evidence_channels.py`（封闭探针类型→四通道**不相交**分区、每通道独立工具视图、独立 evidence_id 空间、`validate_isolation`） |
| A3 | ✅ | `scripts/eval_debate.py`（EXP-DEBATE-001），`RuleRoleAgent` 见 `debate_rules.py`；报告 `reports/debate-eval-controlled-{test,train,validation}.{json,md}` |
| A4 | ✅ | Wilson + 配对 McNemar + Holm（5 个比较）+ ICC/DEFF 有效 n，全部复用 `scripts/stats_inference.py` |
| A5 | ✅ | `docs/competition/fact-sheet.md` F27 / M38 / 口径⑯ |
| 离线确定性角色 | ✅ | `agent/subagents/debate_rules.py`（`RuleRoleAgent`）；真实 LLM 角色**未接入**，`RoleAgent` 已留注入点 |

**门禁结果**：A-G1 ✅（`tests/agent/test_debate.py` 22 passed）、A-G2 ✅（共享证据池负对照判 `valid=False`）、
A-G3 ✅（`n` 与有效 n 同时给，`escalated` 单独计数）、A-G4 ✅（McNemar + Wilson + Holm 齐全）、A-G5 ✅（fact-sheet 口径⑯）。

**核心结论（诚实交底，详见 M38）**：
辩论协议与隔离**已可运行**，但**未证明协议本身带来增益**——
相对单角色的增益**全部来自四通道证据覆盖**（test 上辩论与「全证据单角色」覆盖对照逐样本 **0/48** 不同；
train/validation 上辩论因未收敛**反而更低**）。因此**禁止**写「多 Agent 辩论提升准确率 X%」。

---

## 3. 子项 B：知识图谱 + 神经符号推理机

### 3.1 目标

从 `knowledge` 的 **737 条 catalog**（真实语料，运行时口径）抽取**受控实体类型 + 关系**，建**小规模、可回溯**的图，并实现**符号推理机**：给定告警 → 沿关系找候选根因，输出**可核查推导路径**；与现有 hybrid 检索做对照。

### 3.2 非目标

- 不引 Neo4j / 第三方图数据库（本机与许可成本都不可控）；图用**进程内邻接表 + JSON 落盘**即可。
- 不替换现有 `bm25` / `hybrid` / `vector_store`（它们是召回层，保留）。
- 不做「全量企业知识图谱」这种规模声明——**入库多少条就写多少条**。

### 3.3 设计

**实体与关系（受控词表，先定死再抽）**

| 实体类型 | 示例 | 来源 |
|---|---|---|
| `service` | nginx / mysql / redis | 条目正文与目录名 |
| `component` | 容器 / 副本 / 磁盘 | 条目正文 |
| `alert` | 502 / 磁盘写满 / 证书过期 | 条目标题与 symptom |
| `metric` | cpu / memory / latency | 条目正文 |
| `run` | 发布 / 演练 / 变更 | 条目时间线 |

关系：`depends_on` / `emits`（服务→告警）/ `caused_by`（告警→组件）/ `mitigated_by`（告警→处置）/ `cites`（条目→证据）。

**抽取（诚实优先）**

- 规则抽取（正则 + 受控词表）为主，LLM 抽取为辅；
- 每条边带 `{confidence, source_entry_id, extractor}`；**低于阈值的边不入图**（写 `rejected` 计数，不伪造）；
- 落盘 `reports/kg-extract-<tag>.json`（不入库），含实体数 / 边数 / 拒绝数 / 抽样人工核对结果。

**推理机（纯 Python 符号规则，可解释）**

```
给定 alert A：
  candidates = { C | (A)-caused_by->(C) } ∪ { S | (S)-emits->(A) }
  沿 depends_on 反向扩展 1~2 跳，按「路径条数 + 边置信度」排序
  输出：候选列表 + 每条候选的推导路径（可回溯到 entry_id）
```

**神经符号边界（必须写清）**

- **神经**负责召回与排序（现有 hybrid）；
- **符号**负责可解释推导与硬约束（如「必须有 caused_by 边」）；
- **符号结论必须能回溯到具体边与 entry_id**，否则只能标 `neural_only`，不得写成「符号推理得出」。

**对照实验**：同一批查询，`hybrid recall@5` vs `KG recall@5` vs `hybrid+KG`，给 n、命中定义（与 DS-02 口径对齐）与 Wilson 区间。

### 3.4 工作包

| 包 | 内容 | 产出 |
|---|---|---|
| B1 | `knowledge/graph/schema.py`：实体/关系词表 + 边数据结构（纯 stdlib） | 模块 + 单测 |
| B2 | `knowledge/graph/extract.py`：规则抽取器 + LLM 抽取适配器（缺模型降级为规则） | 模块 + 抽取报告 |
| B3 | `knowledge/graph/store.py`：邻接表 + JSON 持久化 + 落盘/加载 | 模块 + 单测 |
| B4 | `knowledge/graph/reason.py`：符号推理 + 路径回溯 + 硬约束 | 模块 + 单测 |
| B5 | `scripts/eval_kg.py`：hybrid vs KG vs 混合对照（n≥32）+ fact-sheet 登记 | 脚本 + 报告 + 登记 |

### 3.5 门禁

| 编号 | 判据 |
|---|---|
| B-G1 | 词表封闭：抽取器不得产出词表外的实体/关系类型（单测钉住） |
| B-G2 | 边可回溯：每条边有 `source_entry_id`；**抽样 ≥20 条人工核对**并给一致率 |
| B-G3 | 低置信不入图：`rejected` 计数必须落盘；**禁止**把被拒边算进命中 |
| B-G4 | 对照：hybrid / KG / 混合三路 recall@k，n 与 Wilson 齐全；KG 不如 hybrid 时**如实写** |
| B-G5 | 隐私：抽取只用本机模型，**知识条目不出本机**（用户级偏好） |
| B-G6 | 口径：给实体数 / 边数 / 覆盖率（有边的条目占比），**禁止**写「全量知识图谱」 |

### 3.6 风险

1. **抽取幻觉**：LLM 抽出不存在的边。缓解：词表封闭 + 置信度阈值 + 人工抽样 + 拒绝计数。
2. **规模虚报**：737 条里可能只有少数能抽出关系 → 覆盖率必须如实给。
3. **许可证**：若引入新的抽取模型，须按 `design-system/MASTER.md` 先核验（沿用 `reports/open-source-license-verification-<date>.md`）。

---

### 3.7 落地记录（2026-11-22，用户点名「继续」推进 B）

| 包 | 状态 | 产出 |
|---|---|---|
| B1 | ✅ | `knowledge/graph/schema.py`：5 类实体 × 5 种关系**封闭词表** + 受控关键词词表（component 20 / metric 11 / run 11）+ `Entity`/`Edge` 校验（边必带 `source_entry_id`、confidence ∈ [0,1]） |
| B2 | ✅ | `knowledge/graph/extract.py`：声明式 `emits`（条目 `service`）/ `cites`（内层 JSON `relatedIds`）conf **1.0**；规则抽取按**命中位置**分档——症状字段 0.8 / 处置字段 0.4（默认拒收）/ `mitigated_by` 0.6 / `depends_on` 0.6，阈值 `DEFAULT_MIN_CONFIDENCE=0.5` |
| B3 | ✅ | `knowledge/graph/store.py`：进程内邻接表 + 反向索引 + JSON 落盘/加载（**不引第三方图库**） |
| B4 | ✅ | `knowledge/graph/reason.py`：`SymbolicReasoner`，沿 `caused_by` + `depends_on`(反向) + `emits` 扩展 ≤2 跳；**硬约束**：无 `caused_by` 边 → `neural_only`（禁写「符号推理得出」）；每步 `DerivationStep` 带 `source_entry_id` |
| B5 | ✅ | `scripts/eval_kg.py`（EXP-KG-001）+ `tests/scripts/test_eval_kg.py`；报告 `reports/kg-eval-20261122.{json,md}` |
| 单测 | ✅ | `tests/knowledge/test_graph.py` **39 passed**（B-G1/G2/G3 + 图 + 推理硬约束） |

**门禁结果**：B-G1 ✅（词表封闭，单测钉住）、B-G2 ✅（边必带 `source_entry_id`，抽样 24 条核对 1.0000）、
B-G3 ✅（`rejected` 217 条落盘，被拒边不计入命中；**并修复真缺陷**：症状边被高阈值拒收时此前静默丢弃，现也落 `rejected`）、
B-G4 ✅（三路 recall@5 + Wilson + 互补性，n=319）、B-G5 ✅（全程本机，HashEmbedding 离线，条目不出本机）、
B-G6 ✅（双口径覆盖率，fact-sheet 口径⑰）。

**全量事实**：737 条 catalog → 节点 **834** / 边 **1984** / 被拒 **217**；
关系分布 `emits` 737 / `cites` 384 / `caused_by` 416 / `depends_on` 354 / `mitigated_by` 93；
有 `caused_by` 边的条目 **319/737 = 0.4328**（这才是符号推理真实可用面）；
符号推理结果 `derived` 319 / `neural_only` 418。

**核心结论（诚实交底，详见 M39）**：
图谱与符号推理**已可运行**，但**未证明符号侧带来独立的召回增益**——
评测金标由 `caused_by` 图派生，与 KG 候选**同源**，因此 KG 的 hit@5 = 1.0000 与
hybrid+KG 的 +0.0408 增量**都是循环的**，**禁止**写成「混合检索优于 hybrid」。
可确认的只有：符号侧与 hybrid 召回**部分互补**（top-5 平均重叠 0.464 条，仅 KG 命中 66 条），
但无独立真值时**无法量化该互补的价值**。

**关键坑（新踩）**：
1. catalog 条目 `content` 的内层 JSON **仅 244/737 可解析**（另 9 条解析失败、484 条无 JSON 标记）
   → 抽取器靠**顶层 `title`** 兜底，评测脚本若只读内层 JSON 会得到大片空文本（本次踩中并修复）。
2. 「有任意入图边占比」因声明式 `emits` 恒为 **1.0000**，**无信息量**；必须同时给 `caused_by` 覆盖。
3. `KnowledgeService._entry_to_text` 会 `import` 整个 service（重依赖），评测脚本改为自带等价文本组装。
4. `RetrievalResult.document_id` 才是条目 id，`chunk_id` 是 uuid，不含 entry_id。

---

## 4. 子项 C：因果图 / 反事实（最后做）

### 4.1 目标

在现有 6 个根因模型上增加**反事实评测**，把「A@1 增益」从「相关结构下的排序更好」升级为「**对因果干预的响应更符合预期**」，并给出可复核的消融。

### 4.2 反事实构造（**必须先定义判据，否则倍数不可解释**）

三选一或组合，**默认 C1 + C2**：

| 方案 | 构造 | 指标 | 说明 |
|---|---|---|---|
| **C1 特征干预** | 对合成拓扑中真根因节点 `v` 做 `do(x_v ← 0)`（遮蔽其根因特征），其余不变 | `counterfactual_flip_rate` = 模型 top-1 是否**离开** `v` | 因果模型应当在干预后改变排序；相关模型可能不变 |
| **C2 反事实配对** | 同一拓扑、同一噪声，仅**根因节点不同**（`v` vs `w`），构造配对样本 | `pair_accuracy` = 真根因被排在前面的比例 | 配对消除拓扑难度差异，直接测「是否抓住因果特征」 |
| C3 介入式消融 | 逐步遮蔽真根因的因果父节点特征 | A@1 随遮蔽比例下降曲线 | 看因果重要性，不作主判据 |

**主判据**：`A@1_gain = A@1(因果模型) − A@1(相关模型)`，必须 **Holm 校正后显著** 且给**分层 bootstrap 95% CI**；否则结论写 **「未证明增益」**。

**「因果模型」候选（诚实优先，不预设一定成立）**

1. `graphsage` / `gat` + **反事实数据增强**训练（用 C1/C2 生成的样本对做对比学习）；
2. **因果正则**：在损失里加入「干预后排序应改变」的软约束（权重作为超参，消融给 0/0.5/1.0）；
3. 若 1/2 都不显著 → **如实写「因果训练未带来可证增益」**，并保留相关模型为默认。

### 4.3 非目标

- 不声称「生产因果推断」：全部在**合成拓扑 + 合成告警**上，与 M29 口径一致；
- 不做因果发现（PC / GES / NOTEARS），交付周期不够；
- 不替换现有默认模型，除非消融显著。

### 4.4 工作包

| 包 | 内容 | 产出 |
|---|---|---|
| C1 | `ai-service/scripts/build_counterfactual.py`：C1 干预 + C2 配对生成器（固定种子可复现） | 脚本 + 数据卡 |
| C2 | 评测：`ai-service/scripts/eval_counterfactual.py`，输出 `flip_rate` / `pair_accuracy` / A@1 差分 | 脚本 + 报告 |
| C3 | 因果训练变体：反事实增强 / 因果正则（超参消融 3 档） | 训练代码 + 消融表 |
| C4 | 统计收口：复用 `ablation_rootcause_stats.py` 的 bootstrap + McNemar + Holm | 报告小节 |
| C5 | fact-sheet 登记 + 禁止事项 | 登记 |

### 4.5 门禁

| 编号 | 判据 |
|---|---|
| C-G1 | 构造可复现：同种子重跑逐位一致；数据卡写明生成参数 |
| C-G2 | **循环披露**：合成数据的因果结构由生成器给定 → 报告必须写明「结论只说明模型在该生成器下的相对优劣」（沿用 M29 口径⑦） |
| C-G3 | 对照：相关模型 vs 因果变体，Holm 校正后显著才写「增益」；**不显著必须写「未证明」** |
| C-G4 | 有效样本量：给 `n_eff`（M30 的 ICC/DEFF 口径），不得用名义 n 撑区间 |
| C-G5 | 默认不变：除非 C-G3 通过，**线上默认仍是原模型** |

### 4.6 风险

1. **循环论证**：生成器同时决定因果结构与标签 → 必须披露（C-G2）。
2. **反事实指标可被平凡规则刷满**：例如「干预后总是改判」也能拿高 `flip_rate` → 必须同时报告**误伤率**（对非根因节点干预时的改判率），两者一起看。
3. **训练成本**：现有链路 192 runs 已不便宜，因果变体需限 seeds（≥5）与 epochs。

---

## 5. 统一禁止事项（三件共用）

1. **禁止**把合成数据结果写成生产性能或 SLO（沿用 M29 口径⑦）。
2. **禁止**无对照的「能力提升」声明；所有增益必须给对照 + 区间 + 校正。
3. **禁止**把 `NOT_RUN` / `null` 写成 0 或「已达标」。
4. **禁止**在多重比较下只报有利子集（Holm/BH 必须落盘）。
5. **禁止**让辩论角色共享同一证据池（同源循环）。
6. **禁止**把 LLM 抽取的边直接入图而不标置信度与来源。
7. **禁止**把「神经符号」写成「符号推理已完备」——符号只覆盖已声明词表。
8. **禁止**把 `knowledge-review-graph-v1`（UI 视图）当作知识图谱缺口的实现。
9. **禁止**用受控集的生成标签直接证明能力（M31 循环审计仍有效，见口径⑨）。

---

## 6. 推荐落地序（交实现方）

| 步 | 内容 | 最小可交付 | 预计工作量 |
|---|---|---|---|
| 1 | A1 + A2 + A-G1/A-G2 | 辩论协议 + 三判据 + 防同源负对照测试 | 小 |
| 2 | A3 + A4 + A-G3~G5 | n≥32 对照报告 + 口径登记 | 中（受 LLM 延迟约束） |
| 3 | B1–B5 | 词表 + 抽取 + 推理 + 对照 | 中 |
| 4 | C1–C5 | 反事实生成 + 评测 + 因果变体消融 | 大 |

**交付纪律**：每一步完成后更新 `docs/competition/fact-sheet.md`（新编号接续 F26 / M37），并在 `.workbuddy/memory/<date>.md` 记坑。

---

## 7. 与既有文档的关系

- 上游缺口：`docs/design/llm-distill-stack/ARCHITECTURE.md` §1.2（三张 P2 行）。
- 评测口径：`docs/competition/fact-sheet.md`（M29 / M30 / M31 / M33，口径⑦~⑪）。
- 复用件：`scripts/stats_inference.py`、`scripts/ablation_rootcause_stats.py`、`ai-service/scripts/ablation_rootcause.py`、`ai-service/app/training/graph_model.py`、`knowledge/service.py`、`agent/subagents/`。
- 易混件：`docs/design/knowledge-review-graph-v1/`（UI 视图，非推理图谱）。
- 同类方案范式：`docs/design/persona-emotion-input-v1/DESIGN.md`（缺口→方案→工作包→门禁→口径登记）。
