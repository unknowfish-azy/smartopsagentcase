# 口径台账 · fact-sheet（单一事实源）

> 工作包：T1（国赛冲刺总方案 §4）｜测量日期：2026-11-13｜基线提交：`fb17361`
> 使用规则：**凡写进任何一份材料的数字，只能从本表抄，并保留 n= 与状态标注。** 改动本表必须同时给出可复现的来源命令或 `路径:行号`。
> 状态含义：`MEASURED`=本次实跑；`DRAFT`=数据本身未经人工复核；`NOT_RUN`=未执行，只给协议。

## 1. 已核实事实（F01–F09 复核 + 新增）

| 编号 | 事实 | 核实值（以此为准） | 来源 / 复现方式 | 旧值处理 |
|---|---|---|---|---|
| F01 | Python 代码规模 | **22,048 非空行 / 278 文件**（agent 187=14,751；knowledge 53=4,162；ai-service 38=3,135；backend 为 Java，无 Python） | 对四目录 `rglob("*.py")` 统计非空行，2026-11-13 | 旧 16,536 行/244 文件 **废弃** |
| F02 | 前端代码规模 | TS **52 文件 / 2,643 行**（无 .tsx）；实际主体为 **Vue 234 文件 / 38,998 行 + JS 109 文件 / 13,696 行** | `frontend/src` 按扩展名统计（Python rglob+splitlines），2026-11-15 | 旧 Vue 177 文件/22,569 行、JS 78/8,413（2026-11-13）**已过期**；引用时必须注明语种口径 |
| F03 | 自动化测试 | 后端/Agent **pytest 收集 622 用例**；前端 **733 用例通过**（116 个 .test.mjs）；Java 后端 **774 项执行 / 0 失败 / 0 错误 / 1 跳过**（131 测试类） | `frontend/npm test`（2026-11-15，733 passed / 0 failed）；`cd backend && mvn test`（2m31s，2026-11-15，surefire 汇总）；pytest 收集数沿用 2026-11-13 实测（2026-11-20 W8/W9 新增 7 条 pytest 用例：`tests/scripts/test_agent_security_metrics.py` 5 条 + `tests/security_baseline/test_redteam_regression.py` 2 条；当前收集口径见 F21） | 旧 前端 503（2026-11-12）、后端 671 执行数与 126/131 类口径演进；**671 与 126 均废弃，以本行为准** |
| F04 | 领域数据集 | **7 类场景 / 14 条样本**（network 6、job_scheduling 2、storage 2、其余 4 类各 1） | `SmartOps-Dataset/Linux/*.jsonl` 逐行解析 | 与旧值一致 |
| F05 | 数据状态 | **14/14 全部 DRAFT**，未经专家复核 | 同上，`status` 字段计数 | 与旧值一致，红线①继续有效 |
| F06 | 技术文档 | **20 页**（HTML / PDF 同版；新增 P19/P20 增强附录）；8 章沿用原文未独立复核 | `pymupdf.open("docs/competition/technical-document.pdf")` → 20 pages；`python docs/competition/_validate_techdoc.py --pdf`，2026-11-20 | 旧 14 页（2026-11-13）**已过期**；18 页中间版（v2.0）亦作废 |
| F07 | 架构角色 | 6 类目录均存在：planner / executor / inspector / policies / kernel / tools | `agent/` 目录列表 | 与旧值一致 |
| F08 | 纠察层级 | 四级 Rule → Evidence → AI → StateVerifier，顺序执行可复现 | `agent/inspector/pipeline.py:66-123`；AI 级无 LLM 时降级为空发现（`judges/ai_judge.py:21-43`） | 与旧值一致 |
| F09 | 竞赛 AI 技术分项 | 35%（LLM 8 + Agent 8 + RAG 6 + 多模态 5 + 安全 4 + MCP 4） | `README.md` L171-176 | 与旧值一致 |
| F10（新增） | 风险分级实现形态 | **工具级声明式分级**：`RiskClassifier.classify(tool_name)` 仅按工具名映射 LOW/MEDIUM/HIGH/CRITICAL；各工具以 `risk_level` 类属性声明 | `agent/policies/risk.py:15-45`、`agent/tools/shell.py:14`、`agent/policies/policy_engine.py:23` | **不存在自然语言指令级风险分级器**，材料不得写"AI 识别指令风险" |
| F11（新增） | 前端整改入库状态 | 已提交并推送：`864683c`（P0–P3）→ `d8f5148`（执行记录）→ `4046f53`（交付件）→ `fb17361`（口令轮换）；origin/main 一致、工作区干净 | `git log --oneline`、`git status -sb`，2026-11-13 | 总方案 §3.1/§9 的"未 commit"表述 **作废** |
| F12（新增） | 演示账号口令 | `demo_ops` 已轮换，明文不入库，由本机 `.env` 的 `SMARTOPS_DEMO_PASSWORD` 提供；旧口令 401 失效 | `scripts/e2e/ui_pages_snapshot.py:30-46`；2026-11-13 实测新口令登录 200、旧口令 401 | 讲解稿中旧明文已清除 |
| F13（新增） | Java 后端规模与接口数 | main **331 文件 / 36,863 行**；接口 **477 个**（`@*Mapping` 注解）；迁移表 **119 张**（不变） | `backend/src/main` rglob("*.java") 统计；`grep -rE "@(Get|Post|Put|Delete|Patch|Request)Mapping" backend/src/main --include="*.java" | wc -l`；迁移 SQL `CREATE TABLE` 去重计数，2026-11-15 | 旧 321 文件/3.4 万行/422 接口（FCT 快照）**已过期**；119 表与旧值一致 |
| F14（新增） | 语音识别（ASR）能力 | **工具已补齐**：`agent/tools/speech.py`（`speech.to_text`，可插拔栈 vosk→faster-whisper→whisper→内置 DTW 命令词基线→确定性降级，不伪造转写）；**训练/评测管线就绪**：`scripts/build_asr_dataset.py`（默认 ZipVoice 离线 TTS 合成真实中文语音，复用省赛视频同款模型；备用 sapi/synthetic）→ `train_asr_baseline.py`（DTW 中位模板 + 静态/差分特征）→ `eval_asr.py`（**dev+holdout 双集合强制**） | **真实语音实测（2026-11-16，ZipVoice 合成 10 命令 × 9 变体冻结集）**：dev **38.33%**（23/60）/ holdout **26.67%**（8/30），10 类随机基线 10%；明细 `reports/t-asr-2026-11-16/eval_summary.json`。合成自检（synthetic 扫频）dev/holdout 100% 仅为管线正确性验证，**模板 dataset_mode=synthetic 被工具强制拒用** | **禁引用合成 100% 作为语音准确率**；轻量 DTW 基线真实水平仅约 27%（holds），**不达实用门槛**——可用识别需装 vosk/whisper（可插拔栈已就绪）；真实指标必须双集合同报 |

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
4. `06-工程整改/` 目录下所有文档（口径台账、README-交付、整改对照差分）的假成功 F1=.6667 均为 2026-11-03 扩词表前旧规则口径，已标注废弃。当前统一口径：开发集 F1=1.0（样本内过拟合，禁用于答辩泛化），留出集 F1=0.4762/R=0.3333（n=20，真实泛化）；静默放过=0。
5. `docs/competition/ops-defense-v6.md` 假成功段落已修正为开发集/留出集双口径。`docs/competition/defense-qa.md` Q18 已修正为引用 eval_results.csv 真实数据。
6. `06-工程整改/numeric_consistency.csv` 为 2026-11-03 历史审计快照，`frontend_tests=458`（456 passed / 2 failed）已过时——当前前端门禁为 503 passed / 0 failed（见 F03）。CSV 本身作历史留存，不修改，引用以 fact-sheet 为准。

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

## 4. W10 安全 × 产品共生增强事实（2026-11-20）

> W1–W9 落地后的新增口径，编号接续 F14 / M05。引用规则不变：**数字必须带 n 与状态**；`NOT_RUN` 不得改写成 0%，也不得写成“已达标”。

| 编号 | 事实 | 核实值（以此为准） | 来源 / 复现方式 | 旧值处理 |
|---|---|---|---|---|
| F15 | 统一 Agent Runtime | **单一执行入口**：chat 与内部事件触发均经 `AgentRuntime` 装配 `security_enabled=True` 的 assembly；ReAct/规划路径共用同一 `AgentExecutor` 与 L0–L3 闸门 | `ai-service/app/services/agent_runtime.py`、`agent/assembly.py`、`ai-service/app/services/chat.py`、`tests/agent/test_agent_runtime_wiring.py`、`ai-service/app/tests/test_agent_runtime_api.py` | 新增；旧“chat 有闸门、ReAct 无闸门”表述作废 |
| F16 | 产品工具总线 | **17 个工具 = 12 只读 + 5 写**。只读：`sentinel.alerts/metrics`、`inspector.events`、`knowledge.search/candidates`、`security.posture/findings`、`servers.list`、`slo.status`、`incidents.list`、`robot.fleet`、`audit.chain`；写：`inspector.event.create`、`knowledge.candidate.submit`、`runbook.draft.create`、`robot.task.create`、`robot.estop` | `agent/tools/builtin/product_bus.py:310-462`、`agent/tools/builtin/product_actions.py:247-359`；契约测试 `tests/agent/test_product_tool_bus.py`、`tests/agent/test_product_actions.py` | 新增；旧“0 个产品工具”作废 |
| F17 | 页面侧翼 | **8 页可发起 Agent 并透传页面上下文**：服务器列表、哨兵、机器人控制台、模型网关、知识空间、纠察中心、事件中心、日志诊断；统一挂载 `AgentCopilotDock.vue` | `frontend/src/components/agent/AgentCopilotDock.vue` 与 8 个 `views/**` 挂载点；`frontend/src/api/trustLedger.ts` | 新增；旧“聊天页单点”作废 |
| F18 | Trust Ledger（可信账本） | 每次 run 落 `agent_run`：intent/risk/status/brief/tool_calls/approvals/result/verification_status/page_context/audit_event_ids；前端抽屉可查详情并一键验链 | `backend/src/main/resources/db/migration/V20261120.2__agent_run_ledger.sql`；`AgentLedgerController`（`/api/agent-ledger/runs`）；ai-service `/api/agent/audit/verify`；`frontend/src/components/agent/TrustLedgerDrawer.vue` | 新增；旧“审计只在 jsonl、前端不可见”作废 |
| F19 | 事件驱动闭环 | 哨兵告警 → 后端内部触发（**5 分钟防抖**、内部只读白名单、模型探测闸门）→ ai-service `/api/agent/trigger` → 只读诊断 → 产出 `REVIEW` 事件交人审 | `backend/.../AgentTriggerService.java`、`InternalAgentTriggerController.java`、`AgentDiagnosisClient.java`；`ai-service/app/tests/test_agent_trigger.py` | 新增 |
| F20 | 安全基线加固 | L0–L3 基线 + 6 类注入面 + 输出审核 + 审批 + 审计哈希链 + fail-closed；**CL-006 修复**：`mimikatz(?:\.exe)?`，覆盖 `mimikatz.exe` 漏拦 | `agent/security_baseline/baseline.yaml`、`loader.py`、`engine.py`、`audit_rotation.py`、`integrity.py`；`tests/security_baseline/` | 新增；W8 记录的 CL-006 单点漏拦已修复 |
| F21 | 测试与红队新增 | W8/W9 新增 **7 条 pytest**；当前收集 `python -m pytest tests ai-service/app/tests --collect-only -q` = **1,920 条**（tests/ 1,364 + ai-service/app/tests 556，2026-11-20）；红队语料 **82 条 = 66 攻击 + 16 正常** | `tests/scripts/test_agent_security_metrics.py`、`tests/security_baseline/test_redteam_regression.py`、`tests/security_baseline/redteam_corpus.jsonl` | 新增；不替换 F03 的 2026-11-13 历史收集口径，引用时注明日期与命令 |

### 4.1 W8 指标（10 项，`reports/agent_security_metrics_20261120.csv`）

| 编号 | 指标 | 结果 | n | 状态 | 说明 |
|---|---|---|---|---|---|
| M06 | 注入拦截率 | **1.0（60/60）** | 60 | MEASURED | 内置确定性注入语料；非生产流量 |
| M07 | 误杀率（正常命令） | **0.0（0/114）** | 114 | MEASURED | 内置正常运维命令语料 |
| M08 | 高危拦截率 | **1.0（53/53）** | 53 | MEASURED | L0 合规 + L2 运维红线；CL-006 修复后重跑 |
| M09 | 审批覆盖率 | NOT_RUN | 0 | NOT_RUN | 无 `agent_run` 导出；协议见脚本 `--runs-json` |
| M10 | 审计链完整率 | **1.0（1/1 链，1 条事件）** | 1 | MEASURED | 本机 `data/security_audit`；链数口径 |
| M11 | 越权拒绝率 | NOT_RUN | 0 | NOT_RUN | 无账本导出的 PERMISSION 样本 |
| M12 | 工具调用成功率 | NOT_RUN | 0 | NOT_RUN | 同上 |
| M13 | 页面侧翼使用率 | NOT_RUN | 0 | NOT_RUN | 同上 |
| M14 | 写回闭环率 | NOT_RUN | 0 | NOT_RUN | 同上 |
| M15 | 人审时延 | NOT_RUN | 0 | NOT_RUN | 无 `--reviews-json` 人审记录 |
| M16 | 红队拦截率 | **1.0（66/66）** | 66 | MEASURED | `tests/security_baseline/redteam_corpus.jsonl`；含 CL-006 修复验证 |
| M17 | 红队误杀率 | **0.0（0/16）** | 16 | MEASURED | 正常问题/正常运维操作 |

> 口径约束：M06–M08、M16–M17 为**确定性语料实测**，不是生产流量 SLO；M09、M11–M15 为 NOT_RUN，答辩只能引用“未运行”，不得写成 0% 或“全部通过”。效率 3 项（首 token、run 时长、平均工具数）仍引用 M03 与 `scripts/eval_agent_slo.py` 产物，不在本表重复。
> 演示录屏：分镜脚本已更新为 `demo-script.md` §8（W10 三条主线）；实际 MP4 **尚未录制（NOT_RUN）**，需启动三端实机录屏，材料中不得写“演示视频已完成”。

## 4.2 数据集工程事实（2026-11-20）

| 编号 | 事实 | 核实值（以此为准） | 来源 / 复现方式 | 旧值处理 |
|---|---|---|---|---|
| F22 | 受控数据集 v1 | **158 条 = 144 受控 verification + 14 领域 DRAFT**；受控部分为 6 族 × 4 `root_cause_group` × 6 变体，每条带 `ground_truth` + 非空 `state_assertions`；标签分布 FALSE_SUCCESS 48 / SUCCESS 36 / FAILED 30 / UNKNOWN 30 | `python scripts/build_controlled_dataset.py`；`SmartOps-Dataset/Controlled/v1/{schema.json,samples.jsonl,DATA-CARD.md}`；指纹见 `samples.md5` | 新增；F04 的「14 条」仅指 Linux 领域集，口径不变 |
| F23 | 受控集精度 | 144 条受控在分组设计 ICC=0.10（DEFF=1.40）下有效 n≈103，边际误差 **E≈±0.096**；达 ±0.10 需 n=97（未计聚类），达 ±0.05 需 n=385 | `python scripts/dataset_power_sizing.py` → `reports/power-dataset-sizing.{md,json,png}` | 新增 |
| M18 | 泄漏检查（分组切分） | **PASS**（exact / scenario / evidence / root_cause / environment / version 六类命中数全 0） | `python scripts/run_leakage_check.py` → `reports/leakage-grouped.json` | 旧 `NOT_RUN` **作废**（见 `docs/experiments/data-leakage.md`） |
| M19 | 泄漏检查（随机切分负对照） | **LEAKAGE_DETECTED**（scenario 34 / root_cause 24 / environment 35 / version 24） | 同上 → `reports/leakage-random-negative-control.json` | 新增；证明 M18 的 PASS 不是恒真 |
| F24 | 结构化输出约束（DS-04） | `decision_schema.DECISION_SCHEMA` 经 `LLMService._payload` 注入 Ollama `format` / OpenAI `response_format`（未给定时与旧版逐字节等价）；`RATIONALE_CITES_UNKNOWN_REF` 护栏已接入评测链 | `app/services/decision_schema.py`、`app/services/llm.py:575-596`、`app/guard/output_guard.py`；测试 `app/tests/test_decision_contract.py`（15）、`test_llm_response_format.py`（8）、`test_guard_rules.py`（30） | 新增；旧「无 grammar/schema 约束」表述**作废** |

> 口径约束：M18 的 PASS 仅限当前六类键；`near_duplicate` 未实现（恒 0），**不得**写成「语义近重复已排除」。受控集全部 `review_status=unreviewed` / `human_review=PENDING`，**禁止**用于性能结论或模型训练。

## 4.3 基线评测事实（2026-11-20）

| 编号 | 事实 | 核实值（以此为准） | 来源 / 复现方式 | 旧值处理 |
|---|---|---|---|---|
| M20 | EXP-BASELINE-001 受控集基线<br>⚠️ **2026-11-21 效度降级见口径⑨（M31）**：本指标**不得**写成「假成功检测能力」证据 | **`COMPLETED_WITH_LIMITATIONS`**；可判子集（claim 识别为 `asserts_success`）**n=22**：假成功检出 **P=1.0000（12/12）/ R=1.0000（12/12）/ F1=1.0000**、准确率 1.0000（22/22）、UNKNOWN 率 0.0000；TP=12 TN=10 FP=0 FN=0。**有效 n ≤ 4**（口径⑧）；**循环成立**——平凡规则复现 22/22、反极性 0/22 | `python scripts/eval_controlled_baseline.py` → `reports/baseline-controlled-v1.{json,md}`；数据集 `SmartOps-Dataset/Controlled/v1/splits/test.jsonl` | 旧 `NOT_RUN` **作废**；词表+翻译两轮修复后可判 n 由 10 → 22、FP 由 10 → 0 |
| M23 | claim 词表覆盖（陈述式断言） | **UNKNOWN 84 → 0**（144 条全量）：`classify_claim` 补入「已经好了/网络通了/进程在跑/运行正常/是 active 的/免密登录正常/端口已释放」等 39 条陈述式健康短语 + 「延迟异常/磁盘写满/证书过期」等 26 条故障短语；含空白折叠归一化 | `agent/inspector/verifiers/state_verifier.py` `_RESOLVED_PATTERNS`/`_UNRESOLVED_PATTERNS`；回归门禁 `tests/inspector/test_claim_vocabulary.py`（68 条） | 新增；否定优先规则未改，`test_unknown_claim_with_failed_probe_does_not_pass` 仍 uncertain |
| M21 | 探针翻译忠实性 | **1.0000（144/144）**——把受控集 `expected` 断言翻成既有 StateVerifier 扁平信号后，健康度判定与真值 SUCCESS/非SUCCESS 的一致率。达成路径：①`systemd_state` 纳 `active`/`exited`；②`metric_threshold` 低阈值型（命中率）极性修正；③数据集侧补语义位 `port.occupied`/`config_value.expect`/`http_status.expected_status`；④`http_body.contains` 命中改判健康 | 同上（`probe_translation_audit` 段）；回归测试 `tests/agent/test_controlled_probe_adapter.py`（38 条，含忠实性=1.0 断言） | 旧值 0.8125 **作废**；该指标**不等于**真实分布准确率 |
| M24 | 核验器 HTTP 期望状态码通道 | `StateVerifier._probe_healthy` 新增 `expected_status`：调用方显式声明「此路径应返回该码」时命中即健康（旧接口下线→404 是预期），未声明才回落默认 2xx/3xx 规则 | `agent/inspector/verifiers/state_verifier.py` L361 起；测试见 `test_http_expected_status_channel` | 新增；用于消除「404 一律判坏」造成的不可判 |

| M22 | 数据批准门（双标一致率 / κ） | **NOT_RUN**——盲评包已就绪但无人工评分。基础设施经自检：144 条、核心字段一致率与 Cohen's κ（标签+故障族双维度）计算正确，退化分布 κ 返回 null；**未用构造标签冒充复核** | `python scripts/dataset_approval_gate.py --prepare` → `review/pack.jsonl`（sha256 `ae9161df…`）；`--score` 未填表时输出 NOT_RUN；测试 `tests/scripts/test_dataset_approval_gate.py`（8 条） | 新增；§8 门槛 = 一致率 ≥0.90 或 κ ≥0.75 |
| M25 | 统计推断模块 | `scripts/stats_inference.py`：Wilson / Clopper-Pearson / bootstrap（BCa·percentile·basic）/ 精确二项 / McNemar（明确定义 `2·min(P(X≤k),P(X≥k))`）/ Wilcoxon / 配对·独立置换 / Holm-Bonferroni 与 Benjamini-Hochberg / Cohen's h·κ / RR·OR（Woolf）/ ICC(1) / 设计效应 / 样本量反解；scipy 缺失时退化到纯 stdlib 实现（不完全 beta + 二分求分位点）；**48 项单测** | `python -m pytest tests/scripts/test_stats_inference.py`（48 passed）；供基线/消融/功率测算共用，消除各脚本各写一份 Wilson 的口径分叉 | 新增（论文级补强第一环） |
| M26 | 基线显著性与多重比较<br>⚠️ **效度降级见口径⑨（M31）**：McNemar「显著更优」只在平凡规则同样满足的集合上成立 | test 二分类可判子集 n=22：P/R/F1=1.0000，**Wilson 95% 下界 0.7575（12/12）、准确率下界 0.8513（22/22）**；配对 McNemar 对「恒判假成功」**b=10 c=0 p=0.0020（显著更优）**、对「恒判成功」p=0.0005；逐族 vs 机会水平经 **Holm 校正后 0/4 显著**（小样本下「单族全对」不足以称显著）；跨 split 二分类准确率均 1.0000，独立置换 p=1.0000（**诊断口径，不得作性能声明**） | `python scripts/eval_controlled_baseline.py` → `reports/baseline-controlled-v1.{json,md}`（§3/§3.1/§4/§6）；测试 `tests/scripts/test_eval_controlled_baseline_stats.py`（11 条） | 新增；「优于基线」从断言升级为可检验陈述 |
| M27 | Inspector 层级消融（受控集）<br>⚠️ **效度降级见口径⑨（M31）**：「能力全部来自 L4」这一结论在循环成立时仍描述真实机制，但**不构成能力证据** | `EXP-ABLATION-INSPECTOR-001`：A_claim_only（R=0.0000，P 无正类预测→null）/ B+L1（可判 0）/ C+L2（可判 0）/ D_full（n=22，P/R/F1=1.0000）。**结论：假成功检测能力全部来自 L4**；A→D 配对 McNemar b=0 c=12 **p=0.0005（Holm 后仍显著）**；B/C 与 D **不可检验**（无二分类预测），显式记 `NOT_RUN` 而非「无差异」；L2 相对 L1 多 10 条 `HALLUCINATION`（L1 在本受控集零发现，因样本无工具调用轨迹）；B/C 的 `VERIFICATION` issue 属**消融伪影**已在报告标注 | `python scripts/eval_inspector_ablation_controlled.py` → `reports/ablation-inspector-controlled.{json,md}`；测试 `tests/scripts/test_eval_inspector_ablation_controlled.py`（7 条） | 新增；`docs/experiments/evaluation-plan.md` 的 Inspector 消融链首次由 `NOT RUN` 转为受控集 `COMPLETED_WITH_LIMITATIONS` |
| M28 | 复现包 | `repro/`：`environment.py`（解释器/平台/依赖/Git/种子，**不采集主机名与绝对路径**）、`registry.py`（11 件产物逐件 sha256 + 状态/n/seed 解析，9 件必需，缺失即 `complete=false`）、`reproduce.py`（指纹→切分→泄漏→基线→消融→注册表，必需步骤失败即中止并留日志）。一键跑通 **9/9 必需产物就绪** | `python repro/reproduce.py`（约 10s）→ `repro/{environment,registry,reproduce-log}.json`；测试 `tests/scripts/test_repro_bundle.py`（9 条） | 新增 |
| M29 | 根因模型消融统计推断 | `EXP-ABLATION-ROOTCAUSE-STATS-001`：6 模型 × 4 场景 × **8 seeds** = **192 runs**（每单元 320 事件），A@1/A@3/MRR 均给**分层 percentile bootstrap 95% CI**（seed 内重采样事件，5000 次）+ **配对 McNemar**（同一 scenario/seed/event）+ **Holm-Bonferroni 与 BH 双校正**；另给**确定性随机排序基线** `E[A@1]=1/k`、`E[A@3]=min(3,k)/k`、`E[MRR]=H_k/k`。**Holm 校正后显著优于 `heuristic` 的模型数**：static **5/5**、degraded **5/5**、dynamic **2/5**（tgat/tgpm）、**large_graph 0/5**。⚠️ 校正的必要性有两处直接例证：`dynamic_spread` 的 graphsage **raw p=0.0433 却 Holm 0.1298 不显著**；`large_graph` 的 graphsage **raw p=0.0128 却 Holm 0.0639 不显著**（8 seeds 复算仍未通过） | `python scripts/ablation_rootcause_stats.py` → `reports/ablation-rootcause-stats.{json,md}`；数据源 `reports/ablation_rootcause_raw.json`（192 runs）；测试 `tests/scripts/test_ablation_rootcause_stats.py`（12 passed） | 新增；**修正**旧 `reports/m2_ablation_rootcause_analysis.md` 中「GraphSAGE 是大图首选」等未校正断言（大图 raw p=0.0128 → Holm 0.0639，不显著）；3 seeds 时 degraded 的 gat 不显著、8 seeds 下**转为显著**，说明 seeds 数会影响边缘结论 |
| M31 | **标签—探针循环审计** | `EXP-CIRC-001`：**主指标子集上真值标签由「探针健康度」单比特唯一决定**。全量 144 条列联完美对角（探针健康 ⇒ SUCCESS 36；不健康 ⇒ FALSE_SUCCESS 48 / FAILED 30 / UNKNOWN 30），Fisher 精确单侧 **p≈9.1e-13**；二分类分母 n=72 上平凡规则复现 **72/72**、反极性 **0/72**；逐 split（train/validation/test）均为 **平凡规则 28/28、22/22、22/22，反极性全 0**。主指标覆盖率仅 **50%**（68 条 denies_success + 4 条 out-of-taxonomy 被排除出分母） | `python scripts/audit_label_probe_circularity.py` → `reports/label-probe-circularity.{json,md}`；测试 `tests/scripts/test_validity_audits.py`（11 passed，含循环检出的回归保护） | 新增；脚本在循环成立时返回非零，可作门禁。**定性**：不是数据造假（生成器自陈合成），而是**指标被误用为能力证据**——P/R/F1=1.0 等价于 `prediction=f(probe_health)` |
| M32 | 措辞独立性审计 | `EXP-WORDING-001`：24 组每组 **2 场景 × 3 模板**，唯一 claim 串 3–6 条/组，跨场景模板复用率均值见报告；按变体切分后两侧**精确重叠 13 条**、≥8 字符公共片段 **645 个** → **措辞层留出不可行**（`wording_holdout_feasible=false`）。同组配对一致性（单位=`root_cause_group`，n=24）：两侧均全对 12 组、一致率 0.50 | `python scripts/build_wording_holdout.py --write` → `reports/wording-holdout.{json,md}`；同上单测 | 新增；说明受控集变体是**模板复述**而非独立措辞样本，且词表与评测集同源 → 措辞泛化未检验 |
| M30 | 分组相关（ICC）与设计效应 | `EXP-ICC-001`：受控集 test 按 `root_cause_group`（**8 组 × 6 条**）算 ICC(1)。**组内判定完全同质** → ICC 点估计 **1.0000**，但组内方差为 0 令 ANOVA 区间**退化**（不可当作「已证明完全相关」）；全样本 DEFF=6.00 → **n_eff=8.0**。**主终点二分类子集 n=22 仅覆盖 4 个 `root_cause_group` → 有效样本量上界 4**（名义 n 显著高估信息量，Wilson 区间偏窄）。附 DEFF 敏感性表与「达 ±0.05 所需 n」（本 DEFF 2305 / DEFF=2 769） | `python scripts/icc_design_effect.py` → `reports/icc-design-effect.{json,md}`；`stats_inference` 新增 `f_ppf`/`icc_ci_one_way`（经 Beta 变换，scipy 缺失可退化）；测试 `tests/scripts/test_icc_design_effect.py`（14 passed） | 新增；把 `baseline-controlled-v1.md` §8-7 的「ICC 未测」由 `NOT_RUN` 转 `MEASURED`；**不做事后功效**。**多口径交叉验证**：`root_cause_group`/`family`/`variant_of` 三口径的全样本 n_eff 分别为 **8.0 / 7.6 / 16.0**，均远低于名义 48；主终点子集有效 n 上界取最保守 **4** |
| M33 | LLM 判定基线（qwen3:1.7b）<br>⚠️ **与 M20 是两条不同链路**：本项是真实 LLM 评测，**不得**与确定性 Inspector 管线（M20，`is_llm=false`）混填或互相引用数值 | **`RUN`**（`EXP-LLM-BASELINE-2026-11-21`，`dataset_version=smartops-eval-v1`，`data_class=SYNTHETIC`）：32 条 DS-02 用例（counter/gap/guard/normal 各 8）**6 项有实测值**——task_success **0.4688**（15/32）、evidence_accuracy **0.8125**（26/32）、hallucination_rate **0.0000**、false_success_rate **0.2083**（5/24）、safety_violation_rate **0.0000**（0/32）、latency **5454.8ms（单次均值，非分位）**；**其余 8 项保持 null / `NOT_RUN`**（root_cause/tool/risk/approval/verification 无用例真值；inspector P/R 属 M20 实验；token_cost 未采集） | `python ai-service/scripts/bench_llm_eval.py --provider ollama --model qwen3:1.7b --no-schema` → `data/training/eval/{baseline-report.json,latest.json,report-2026-11-21.md}`（后两者不入库）；LoRA 已入 MySQL 台账（training_run id=8 FAILED / id=9 COMPLETED，evaluation_run id=14 0.4375 / id=15 0.7188）；逐项口径见 `docs/experiments/baseline-report-closure.md` | 新增；旧「14 项全部 null、status NOT RUN」表述**作废**。**禁止**说成「14 项全部收口」，**禁止**把 null 写成 0，**禁止**把 M20 的 P/R=1.0 当成本项成绩 |
| M34 | 结构化输出实测（DS-04）<br>⚠️ **遗留偏差见口径⑫**：`required` 缺 `label`/`confidence`，与训练形状不同形 | **`RUN`**（`EXP-DS04-2026-11-21`，qwen3:1.7b，n=32，带 schema）：`json_valid_rate=1.0000`、`hallucination_rate=0.0000`、`safety_violation_rate=0.0000`；`pass_rate=0.5000`（16/32）vs 无 schema 基线 0.4375（15/32）。三次数值有运行间波动（旧轮 0.5625），**n=32 单次运行，不声明显著性** | `python ai-service/scripts/bench_llm_eval.py --provider ollama --model qwen3:1.7b --tag ds04-verify` → `latest-ds04-verify.json`；验收记录 `.trae/documents/DS-04-结构化输出约束验收记录-2026-11-21.md`；守卫测试 `app/tests/test_decision_contract.py`（15 passed） | 新增；DS-04 三条断言（json_valid≥0.98 / halluc≤0.02 / json_valid 不低于基线）均达标 |

> 口径约束（四条硬边界）：
> ①**非 LLM**：模型成分是确定性 `InspectorPipeline`（Rule+Evidence+AI降级+StateVerifier），`is_llm=false`，不得写成模型能力。
> ②**数据集未批准**：受控集全 `review_status=unreviewed` / `human_review=PENDING`，**approved=False**，本结果不得引用为「approved 基准」。
> ③**词表已补齐陈述式断言（2026-11-20）**：原词表仅覆盖「动作完成 + 恢复」两类措辞，144 条中 84 条落 unknown；补入真实措辞后 **unknown 归零**，可判子集由 n=10 扩至 n=22。未覆盖措辞仍 fail-closed 落 UNKNOWN，否定优先规则不变。
> ④翻译忠实性已达 **1.0000（144/144）**；此前的 0.8125 根因已逐条定位并修复（systemd `active` 缺失、metric 极性反转、语义位缺失），**不是**随机误差。该指标度量「归一化健康度与真值 SUCCESS 是否一致」，**不等于**真实分布准确率。
> ⑤**claim 语义歧义**：`denies_success` + 探针不健康时核验器判 `passed=True`，脚本映射为 SUCCESS；此类 claim 可能是「故障仍在」也可能是「否定式正面陈述」（如「配置不再漂移」真值 SUCCESS），故全样本一致率 0.5000 仅作参考，**不可用于断言分类准确率**。
> ⑥**二分类子集口径（2026-11-21）**：P/R/F1 只在「claim=asserts_success 且真值 ∈ {SUCCESS, FALSE_SUCCESS} 且预测 ∈ {SUCCESS, FALSE_SUCCESS}」的子集上计算；真值为 FAILED/UNKNOWN 的可判样本**单独计数披露**（test 0 条、validation 4 条），**不进 P/R/F1 分母**——否则准确率与 P/R 会互相矛盾。
> ⑦**消融统计口径（2026-11-21，M29）**：根因消融全部在**合成图谱**（随机拓扑 + 合成告警）上，结论只说明「模型在该生成器下的相对优劣」，**不得**写成真实生产性能；seed=**8**（<10），分层 bootstrap 在每个 seed 内重采样事件但**层数过少、seed 间方差仍估计不足**，区间不得写成高精度；`large_graph` 场景**无任何模型在 Holm 校正后显著优于 `heuristic`**（gat raw p=0.0135 方向为负 → Holm 0.0677），**不得**声称大图存在可用模型或「GraphSAGE 为大图首选」。
> ⑧**分组相关口径（2026-11-21，M30）**：受控集 test 的 48 条**组内判定完全同质**，主终点二分类子集 n=22 **只覆盖 4 个 `root_cause_group`**，**有效样本量上界为 4**。因此：①M20/M26/M27 的 Wilson 区间**偏窄**，引用时必须同时给出「有效 n ≤ 4」；②**不得**用 ICC=1.0000 宣称「已证明样本独立相关」——组内方差为 0 令区间退化，只可说「样本内无组内变异可估」；③扩样本必须**增加 `root_cause_group` 数量**而非仅增加变体，否则有效 n 不增长。
> ⑨**效度红线（2026-11-21，M31/M32，最高优先级）**：**主指标子集的真值标签可由「探针健康度」单比特唯一决定**——全量 144 条中探针健康 ⇒ `SUCCESS`、不健康 ⇒ `FALSE_SUCCESS`/`FAILED`/`UNKNOWN`（列联完美对角，Fisher 精确单侧 p≈9.1e-13）；在主指标二分类分母（n=72）上平凡规则「不健康 ⇒ FALSE_SUCCESS」复现 **72/72**，反极性对照 **0/72**。含义：`EXP-BASELINE-001` 的 P/R/F1=1.0000 **不需要任何 claim 语义理解**，等价于 `prediction = f(probe_health)`，而标签本身由同一输入构造 → **循环论证**。因此：①**禁止**把 M20/M26/M27 的任何 P/R/F1 写成「假成功检测能力」证据，只能写成「探针归一化链路自洽性」证据；②生成器 `LABEL_CONTRACT`（`build_controlled_dataset.py:519`）已自陈「标签由探针断言直接推出」，DATA-CARD 亦声明合成性质，**这不是数据造假，而是指标被误用为能力证据**；③修复前提是引入**对抗单元**（探针健康但标签非 SUCCESS / 探针不健康但标签 SUCCESS），并由独立观测或人工判定产生标签。
> ⑩**措辞泛化未检验（2026-11-21，M32）**：24 组每组仅 **2 场景 × 3 模板**（唯一 claim 串 3–6 条/组），按变体切分后两侧仍精确重叠 **13 条**、≥8 字符公共片段 **645 个** → **措辞层留出不可行**；且词表本身取自这 144 条 claim，**词表与评测集同源**。故受控集指标只能说明「同模板复述下判定稳定」，**不得**声称措辞泛化。
> ⑪**LLM 基线口径（2026-11-21，M33）**：`EXP-LLM-BASELINE-2026-11-21` 的 `baseline-report.json` 14 项中**只有 6 项有实测值**，其余 8 项为 `null`/`NOT_RUN`。因此：①**禁止**说成「14 项全部收口」「评测基线全绿」；②**禁止**把 null 写成 0 或「已达标」；③`latency=5454.8ms` 是 **n=32 的单次均值**，**不是** p50/p95，**不得**当 SLO 或时延分位引用；④本项与 M20 是**两条不同链路**（真实 LLM vs 确定性 Inspector），数值**不得**互相填充或合并成单一分数；⑤`token_cost` 待 runner 采集 Ollama `usage` 后补，补齐前保持 null。
> ⑫**结构化输出口径（2026-11-21，M34/F24）**：DS-04 实测 `json_valid_rate=1.0000`、`hallucination_rate=0.0000`，`pass_rate` 带 schema **0.5000** vs 无 schema **0.4375**（n=32 单次运行）。因此：①**禁止**把「schema 让通过率大幅提升」当结论——15/16/18 条的三轮波动属同模型运行间方差，且 n=32 不足以谈显著性；②**必须同时说明遗留偏差**：`DECISION_SCHEMA.required` 缺 `label`/`confidence`，故带 schema 时模型 32/32 条省略这两个字段，计划要求的 `INSUFFICIENT→label=null` 约束在推理侧空转、训练与推理形状不同形；③`json_valid_rate` 基线本就 1.0，DS-04 断言③「上升」按「不得低于基线」判定，**不得**写成「提升了解析成功率」。

## 5. 红线（沿用，优先级最高）
1. 数据集 14 条全 DRAFT → 禁写"准确率 9X%"；用"链路打通 + n= 小样本 + 局限声明"。
2. 未完成实验标 NOT_RUN 并给协议，只呈现已完成项；禁止只报有利子集。
3. 规则基线组件（Planner/BM25/向量/AI Judge）统一写"确定性基线 + 可插拔接口"。
