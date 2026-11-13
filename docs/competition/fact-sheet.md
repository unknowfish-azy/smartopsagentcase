# 口径台账 · fact-sheet（单一事实源）

> 工作包：T1（国赛冲刺总方案 §4）｜测量日期：2026-11-13｜基线提交：`fb17361`
> 使用规则：**凡写进任何一份材料的数字，只能从本表抄，并保留 n= 与状态标注。** 改动本表必须同时给出可复现的来源命令或 `路径:行号`。
> 状态含义：`MEASURED`=本次实跑；`DRAFT`=数据本身未经人工复核；`NOT_RUN`=未执行，只给协议。

## 1. 已核实事实（F01–F09 复核 + 新增）

| 编号 | 事实 | 核实值（以此为准） | 来源 / 复现方式 | 旧值处理 |
|---|---|---|---|---|
| F01 | Python 代码规模 | **22,048 非空行 / 278 文件**（agent 187=14,751；knowledge 53=4,162；ai-service 38=3,135；backend 为 Java，无 Python） | 对四目录 `rglob("*.py")` 统计非空行，2026-11-13 | 旧 16,536 行/244 文件 **废弃** |
| F02 | 前端代码规模 | TS **52 文件 / 2,509 行**（无 .tsx）；实际主体为 **Vue 177 文件 / 22,569 行 + JS 78 文件 / 8,413 行** | `frontend/src` 按扩展名统计，2026-11-13 | 旧 2,245 行/49 文件仅指 TS 且已过期；引用时必须注明语种口径 |
| F03 | 自动化测试 | 后端/Agent **pytest 收集 622 用例**；前端 **503 用例通过** | `python -m pytest tests --collect-only -q`（67.73s，2026-11-13）；`frontend/npm test`（2026-11-12，503 passed / 0 failed） | 旧 108 用例/8 域 **废弃** |
| F04 | 领域数据集 | **7 类场景 / 14 条样本**（network 6、job_scheduling 2、storage 2、其余 4 类各 1） | `SmartOps-Dataset/Linux/*.jsonl` 逐行解析 | 与旧值一致 |
| F05 | 数据状态 | **14/14 全部 DRAFT**，未经专家复核 | 同上，`status` 字段计数 | 与旧值一致，红线①继续有效 |
| F06 | 技术文档 | **14 页**已复核；8 章沿用原文未独立复核 | `pypdf.PdfReader("docs/competition/technical-document.pdf")` → 14 pages | 页数一致 |
| F07 | 架构角色 | 6 类目录均存在：planner / executor / inspector / policies / kernel / tools | `agent/` 目录列表 | 与旧值一致 |
| F08 | 纠察层级 | 四级 Rule → Evidence → AI → StateVerifier，顺序执行可复现 | `agent/inspector/pipeline.py:66-123`；AI 级无 LLM 时降级为空发现（`judges/ai_judge.py:21-43`） | 与旧值一致 |
| F09 | 竞赛 AI 技术分项 | 35%（LLM 8 + Agent 8 + RAG 6 + 多模态 5 + 安全 4 + MCP 4） | `README.md` L171-176 | 与旧值一致 |
| F10（新增） | 风险分级实现形态 | **工具级声明式分级**：`RiskClassifier.classify(tool_name)` 仅按工具名映射 LOW/MEDIUM/HIGH/CRITICAL；各工具以 `risk_level` 类属性声明 | `agent/policies/risk.py:15-45`、`agent/tools/shell.py:14`、`agent/policies/policy_engine.py:23` | **不存在自然语言指令级风险分级器**，材料不得写"AI 识别指令风险" |
| F11（新增） | 前端整改入库状态 | 已提交并推送：`864683c`（P0–P3）→ `d8f5148`（执行记录）→ `4046f53`（交付件）→ `fb17361`（口令轮换）；origin/main 一致、工作区干净 | `git log --oneline`、`git status -sb`，2026-11-13 | 总方案 §3.1/§9 的"未 commit"表述 **作废** |
| F12（新增） | 演示账号口令 | `demo_ops` 已轮换，明文不入库，由本机 `.env` 的 `SMARTOPS_DEMO_PASSWORD` 提供；旧口令 401 失效 | `scripts/e2e/ui_pages_snapshot.py:30-46`；2026-11-13 实测新口令登录 200、旧口令 401 | 讲解稿中旧明文已清除 |

## 2. 评测结果摘要（明细见 `docs/competition/eval_results.csv`）

| 编号 | 指标 | 结果 | n | 状态 | 证据文件 |
|---|---|---|---|---|---|
| M01 | Recall@3 / MRR | **0.5000 / 0.4286** | 14 | MEASURED（数据 DRAFT） | `reports/t1-20261113/m01_retrieval.csv` |
| M01 补充 | Recall@3 / MRR（含 AI 改写变体） | 0.7000 / 0.6571 | 70（有效独立样本≈14） | MEASURED（变体未人工复核） | `reports/t1-20261113/m01_retrieval_with_variants.csv` |
| M02 开发集 | 假成功检出 P / R / F1 | 1.0 / 1.0 / 1.0（TP=26 TN=21 FP=0 FN=0） | 47 | MEASURED（冻结合成集，非真实分布） | `reports/t1-20261113/m02_metrics.json` |
| M02 留出集 | 假成功检出 P / R / F1 | **0.8333 / 0.3333 / 0.4762**（TP=5 TN=4 FP=1 FN=10；uncertain 占 50%） | 20 | MEASURED（留出集，更能代表泛化短板） | `reports/t1-20261113/m02_holdout_metrics.json` |
| M02 | 执行闸 / 人工队列证据 | NOT_RUN | 0 | NOT_RUN（无平台证据输入） | 同上 `execution_gate` 字段 |
| M03 | 首 token 时延 P50/P95 | **3589.6 ms / 4522.5 ms**（mean 3494.4） | 20（20/20 成功） | MEASURED（Ollama qwen3:1.7b，本机 CPU） | `reports/t1-20261113/m03_metrics.json` |
| M03 | 流式完成时延 P50/P95 | 6839.5 ms / 9096.4 ms（mean 6682.7） | 20 | MEASURED | 同上 |
| M03 对照 | 首个 SSE 事件 P50 | 16.6 ms（框架 run 事件，**不是模型输出，禁止当时延成绩引用**） | 20 | MEASURED | 同上 |
| M04（口径A） | 工具级风险声明一致性：准确率 | **0.7619（16/21）** | 21（全量枚举，非 30 抽样） | MEASURED | `reports/t1-20261113/m04_metrics.json` |
| M04（口径A） | 需审批操作被分类器低估 | **3/3**：docker.compose、docker.restart、redis.restart 均被判 LOW | 3 | MEASURED（双轨不一致，不等于已发生越权） | `reports/t1-20261113/m04_risk_consistency.csv` |
| M05 | 人工盲评均分 / Cohen's κ | NOT_RUN | 0 | NOT_RUN：需 3 名真人评者；κ 脚本与空白评分表已备 | `scripts/eval_blind_review.py`、`reports/t1-20261113/m05_ratings_template.csv` |

## 3. 冲突、口径修正与待执行协议

### 3.1 必须回填到既有材料的更正
1. `submission-master-plan.md` F01/F02/F03 旧值作废，统一改抄本表。
2. `国赛冲刺总方案-20261113.md` §3.1「前端整改未 commit」、§3.2 T9 首要动作、§9 风险行均已过时（见 F11）。
3. M02 引用时必须**同时给开发集与留出集**：只报 1.0 属于红线②"选择性呈现"。留出集召回 0.3333 是技术报告 §8 局限的真实素材。

### 3.2 M01 口径
脚本：`python scripts/eval_retrieval.py --output <csv>`（`--include-variants` 为补充集）。答案真值来自数据集 `knowledgeIds`，故指标受 DRAFT 数据质量约束；70 变体为 AI 生成未复核，**有效独立样本约 14，不得当作 n=70 的统计显著性**。

### 3.3 M03 已实测（2026-11-13）
环境：`ollama serve` + `ollama pull qwen3:1.7b`；knowledge(8002) 用 BGE `bge-small-zh-v1.5`（16 篇语料 299 chunks）；ai-service(8001)。
命令：`python scripts/eval_chat_latency.py --requests 20 --output <csv> --metrics-json <json>`。
两个启动要点（复跑必备）：① knowledge 不自动读根 `.env`，必须在进程环境里显式给 `KNOWLEDGE_API_KEY`，否则 fail-closed 拒绝启动；② ai-service 的 run token 用 `.env` 共享密钥按 `v1.<b64(payload)>.<b64(hmac)>` 本地签发，单次使用，因此口径不含 Java 边缘登录/签发。
**口径陷阱（已修正）**：首个 SSE 事件是框架 `run` 事件（P50 16.6ms），其后还有 `thinking`；真实模型输出以首个 `token` 事件为准（P50 3589.6ms）。引用时延只能用 first_token / total，并注明本机 CPU 推理、非生产 GPU。

### 3.4 M04 已按口径 A 执行（2026-11-13 裁决）
脚本：`python scripts/eval_risk_classification.py --output <csv> --metrics-json <json>`。
样本为**全量可枚举操作 21 个**（核心工具 3 + 已安装插件 18），不是原方案的 30 抽样；n=21 即为 100% 覆盖，不凑数。
结果：准确率 0.7619（16/21）；混淆 HIGH→LOW 2、MEDIUM→LOW 2、LOW→MEDIUM 1。
**关键发现**：3 个 `approval_required=true` 的操作（docker.compose、docker.restart、redis.restart）被 `RiskClassifier` 全部判为 LOW。实际审批链读取的是工具/manifest 声明（`policy_engine.py:23`），所以这是"双轨不一致"的潜在风险，**不能写成"已发生越权执行"**，也不能据此声称分类器可靠。
材料口径：风险能力按 F10 的工具级声明描述；本结果可用于"为什么保留人工审批双闸"的论证，禁止改写成"AI 指令风险识别准确率"。

### 3.5 M05 协议（待 3 名真人）
30 条回答脱敏编号，3 名评者独立按 1–5 分评有用性/准确性/可信度，填 `m05_ratings_template.csv` 后运行 `python scripts/eval_blind_review.py --ratings <csv>`，输出各维度均分与两两 Cohen's κ。κ>0.6 方可写"一致性良好"。

## 4. 红线（沿用，优先级最高）
1. 数据集 14 条全 DRAFT → 禁写"准确率 9X%"；用"链路打通 + n= 小样本 + 局限声明"。
2. 未完成实验标 NOT_RUN 并给协议，只呈现已完成项；禁止只报有利子集。
3. 规则基线组件（Planner/BM25/向量/AI Judge）统一写"确定性基线 + 可插拔接口"。
