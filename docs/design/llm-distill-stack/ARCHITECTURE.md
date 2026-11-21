# LLM 蒸馏与感知插件栈 架构方案 v1

日期：2026-11-15
上位依据：`design-system/MASTER.md`（Open Source Intake 条款）、`docs/design/recovery-contract-v1/semantics.md`（证据纪律）
实施计划：`.trae/documents/LLM蒸馏与换底座-DS-01至DS-08实施计划.md`

---

## 0. 结论先行（三句话）

1. **你列的这套 AIOps 神经网络栈，项目里已经建了约八成。** `app/services/` 27 个 service、`app/training/` 11 个模型定义、`scripts/` 9 个 `train_*`、`agent/security_baseline/`（三道锁）、`agent/recovery_contracts/`（一本账）、`ablation_study.py`（消融）全都在。**再让 Trae 按那份清单去"实现"，大部分是在重造轮子。**
2. **真缺口只有四处（2026-11-18 复核后修订，见 §1.1.1 / §1.2）**：① 有 SFT **数据**入口，但没有 **LoRA 训练器**；② 有 732 条知识型 QA，但没有「证据包 → 判定」的任务化样本；③ 有 14 项评测指标口径，但从未跑出基线；④ 1.7B 底座没有结构化输出约束，所以它只能"聊聊"，不能"判定"。
3. **「爬大量数据代替千问迷你模型」这条路线不成立**——数据量替换不了模型能力，而且换底座在你项目里**已经是纯配置项**（`LLM_PROVIDER` / `LLM_MODEL` 两个环境变量），不需要"重构"。

---

## 1. 家底实测（observed：读文件确认，未读实现细节）

### 1.1 你列出、项目里已存在的

| 你清单里的条目 | 项目落点（实测路径） | 状态 |
|---|---|---|
| AnomalyTransformer | `app/services/anomaly_detector.py`、`app/training/anomaly_transformer.py`、`scripts/train_p01_anomaly_transformer.py` | ✅ 有实现+训练脚本 |
| GAT / GCN / GraphSAGE 根因 | `app/services/rootcause_detector.py`、`app/training/graph_model.py`、`gat_model.py`；权重 `models/rootcause_{gat,gcn,graphsage}.pt` | ✅ 有实现+权重 |
| TGAT 时序图 | `app/services/tgat_detector.py`、`training/tgat_model.py`、`scripts/train_tgat.py`、`models/tgat.pt` | ✅ |
| TraceFormer 调用链 | `app/services/trace_detector.py`、`training/trace_model.py`、`scripts/train_trace.py`、`models/traceformer.pt` | ✅ |
| PatchTST 时序预测 | `app/services/forecast_detector.py`、`training/patchtst_model.py`、`scripts/train_patchtst.py` | ✅ |
| 日志语义/分类 | `app/services/log_classifier.py`、`training/log_model.py`、`scripts/train_p12_log_classifier.py` | ✅ |
| TGPM 时序-图融合 | `app/training/tgpm_model.py` | ✅ |
| LLM 增强 GNN（知识先验） | `app/services/knowledge_prior.py`（`/knowledge-prior-info` 端点） | ✅ |
| 时序大模型（语义化诊断） | `app/services/temporal_narrator.py`（`/temporal-narrator-info`） | ⚠️ 有，是否真走 LLM 语义需核 |
| 思维树 + 价值网络 | `app/services/thought_tree.py`、`scripts`… | ✅ |
| RL 处置策略 | `app/services/rl_policy.py`（+ `/rl-policy-info`） | ✅ |
| 持续学习 | `app/services/continual_learner.py`（+ `/continual-learning-info`） | ✅ |
| 故障传播仿真 | `app/services/fault_propagation.py`（+ `/fault-propagation-info`） | ✅ |
| 处置动作风险评估 | `app/services/action_predictor.py`、`training/action_model.py`、`scripts/train_p21_action_effect.py` | ✅ |
| 情景记忆检索 | `app/services/memory.py`、`case_retriever.py`（`train_p13_case_retrieval.py`）；`agent/memory/{short,long}_term.py` | ✅ |
| RAG / Embedding | `app/services/rag.py`；`knowledge/embedding/{bge,sentence_transformer,hash}*`、`retrieval/{hybrid,bm25,vector_store,version_filter}` | ✅ |
| 多模态/仪表盘识别 | `app/vision/{screening,grounding,weak_label,dataset}.py`、`models/yolo26n.pt`、`VLM=glm-4v-plus` | ✅ |
| 世界模型（雏形） | `app/services/simulator.py`、`training/simulator.py` | ⚠️ 有雏形 |
| 神经对齐护栏 | `ai-service/app/guard/{input,output,policy,rules,contract}.py`；`agent/safety/*` | ✅ |
| 三道锁 | `agent/security_baseline/{redlines,robot_guard,audit_sink,integrity,compliance}.py` | ✅ |
| 一本账 | `agent/recovery_contracts/*`、`scripts/training_ledger.py` | ✅ |
| 消融实验 | `scripts/ablation_study.py`、`ablation_rootcause.py` | ✅ |
| 合成数据 | `scripts/gen_synthetic_metrics.py` | ✅ |

> 这张表是**文件名级观测**。每个模块的"实现到什么程度、指标多少"必须逐个跑 `bench_*` / `ablation_*` 才知道，本方案不替它们下结论。

### 1.1.1 补充实测（2026-11-18）：LLM 侧已有资产

§1.1 只扫了 `ai-service/app/services/`，漏掉了仓库根部的 `scripts/` 与 `training/`。下表同样是读文件确认，不是推测。

| 能力 | 项目落点（实测路径） | 状态 |
|---|---|---|
| SFT 数据集构建 | `scripts/build_sft_dataset.py`：151 篇文档 → 217 个合格段落 → 732 条 chatml | ✅ 已产出 `data/training/sft/bailian/smartops-ops-qa-v0.2.jsonl`（624 运维问答 + 108 人工日常对话） |
| 训练/推理 prompt 对齐 | `build_sft_dataset.py` 用 `ast` 从 `ai-service/app/services/chat.py` 抽 `SYSTEM_PROMPT` 与 user 模板，取不到直接报错 | ✅ 逐字节对齐，不手抄 |
| 评测集防污染 | 构建时排除 `knowledge/evaluation/golden_set.json` 的全部问题 | ✅ |
| 训练样本 schema | `training/schemas/smartops-training-sample.schema.json`：`task_type` 含 `EVIDENCE_VERIFICATION` / `OPS_REASONING` / `RISK_DECISION` / `TOOL_SELECTION` 等，`expected_behavior.evidenceOutput` 定义 `{label, reason, supporting_evidence, confidence}` | ✅ 已定义，**但没有数据** |
| 数据集治理 | `training/{dataset_governance,dataset_validator,leakage_checker,dataset_splitter,manifest}.py` | ✅ |
| 评测骨架 | `training/{evaluation_runner,evaluator,baseline_runner,independent_benchmark,layered_gate}.py` | ✅ 有骨架，无用例 |
| 评测指标口径 | `data/training/eval/baseline-report.json`：14 项指标（`task_success` / `root_cause_accuracy` / `evidence_accuracy` / `tool_accuracy` / `risk_accuracy` / `approval_accuracy` / `verification_success` / `inspector_precision` / `inspector_recall` / `hallucination_rate` / `false_success_rate` / `safety_violation_rate` / `latency` / `token_cost`） | ⚠️ **`status: RUN`**（`EXP-LLM-BASELINE-2026-11-21`，qwen3:1.7b，n=32）：**6 项有实测值**（task_success 0.4688 / evidence_accuracy 0.8125 / hallucination_rate 0.0 / false_success_rate 0.2083 / safety_violation_rate 0.0 / latency 5454.8ms），**其余 8 项仍 null**（无用例真值或未采集）。逐项口径见 `docs/experiments/baseline-report-closure.md` |
| canonical JSON / digest | `agent/recovery_contracts/models.py::canonical_json` / `digest_of` / `object_digest` | ✅ 已实现，已被 `receipts.py` 使用 |
| 合成事件样本 | `data/training/candidates/` 40 条，含 `evidence[{evidence_id, source, timestamp, relevance, support_relation, evidence_status, confidence}]` | ⚠️ 证据字段已成形，`expected_behavior` 未铺开 |

### 1.2 真正缺的（2026-11-18 复核后修订）

| 缺口 | 证据 | 价值判断 |
|---|---|---|
| **LLM 训练器（LoRA/SFT 执行）** | `scripts/` 与 `ai-service/scripts/` 各 9 个 `train_*` 全是神经网络；`build_sft_dataset.py` 只造数据不训练 | **P0**，这是"蒸馏换底座"的唯一真通道 |
| **任务化样本（证据包 → 判定）** | 732 条 SFT 全是知识型 QA；40 条 candidates 有 `evidence[]` 但 `expected_behavior` 未铺开；`smartops-training-sample.schema.json` 已定义 `EVIDENCE_VERIFICATION` 却无一条数据 | **P0**，DS-03 的全部实活 |
| **可机判的判定评测用例 + 基线分数** | 用例已有 32 条（四类各 8），基线已跑：`EXP-LLM-BASELINE-2026-11-21`（qwen3:1.7b，n=32）6 项有值、8 项 null。**仍缺** root_cause/tool/risk/approval/verification 的真值字段与 token 采集 | **P0→已部分闭环**，剩余缺口见 `docs/experiments/baseline-report-closure.md` §5 |
| **结构化输出约束** | 已落地：`app/services/decision_schema.py` + `LLMService._payload` 注入 Ollama `format` / OpenAI `response_format`；`RATIONALE_CITES_UNKNOWN_REF` 护栏已接入评测链。实测（`EXP-DS04-2026-11-21`，n=32）：json_valid 1.0000、hallucination 0.0000、safety_violation 0.0000。⚠️ 遗留：`required` 缺 `label`/`confidence`，与训练形状不同形，见 §3.2 与 `.trae/documents/DS-04-结构化输出约束验收记录-2026-11-21.md` | **P0→已闭环**（遗留偏差单独立项） |
| **统一证据封套** | `app/schemas/*.py` 是 17 个各自独立的 domain schema；`training` 侧另有一套 `evidence` 定义，两套不互通 | **P1**，封套要与 `training` 侧字段**映射**，不能另造一套 |
| 因果 GNN / 反事实 | 未找到 | P2，A@1 增益需消融证明 |
| 知识图谱 + 神经符号推理机 | `knowledge/` 有 catalog，无图谱/推理机 | P2 |
| 多 Agent 辩论 | `agent/subagents/` 有 log_diagnosis/patrol，无 debate 收敛 | P2 |
| CAV / NAS / 动态稀疏 / 分布式共识 / 神经规则归纳 / 对抗鲁棒 | 未找到 | P3，赛道题，不建议在交付周期内碰 |

---

## 2. 三处必须纠正的判断

### 2.1 「爬大量数据代替千问迷你模型」不成立

模型能力 ≠ 语料体积。1.7B 在 219 条样本上能学到的，是**任务格式**（"给我证据包，我吐这个 JSON"），不是**领域知识**。领域知识你已经有更好的承载方式：`knowledge/retrieval` 的混合检索 + `case_retriever` 的案例召回。把知识硬塞进 1.7B 权重，结果一定是退化：越训越不会说人话，长尾知识还是查不到。

**正确分工**：知识留在检索里，规则留在 `guard`/`redlines` 里，模型只负责「把证据翻译成受约束的结构化判断」。

### 2.2 219 条不足以 LoRA 出知识，但足够 LoRA 出「格式」

这一点是好消息：**你可以用 219 条做种子，让教师模型扩样**。219 × 教师改写 ≠ 219 条训练样本，而是 3k–10k 条任务实例。蒸馏的合法且有效的形态是**用教师模型的输出造数据**，不是抄权重。

⚠️ **合规红线**：教师模型（Kimi / DeepSeek / 商业 API）的服务条款通常禁止"用其输出训练竞品模型"。用作**内部任务的格式与判读对齐**在多数条款下属合理使用，但**必须在 `reports/` 留一份条款摘录**；若条款明确禁止训练，改用本地教师（同机大模型批量生成，不经过外部 API）。

### 2.3 换底座已经是配置项，不是重构

`app/services/llm.py` 第 22–79 行：`settings.llm_provider` 分派 `mock` / `ollama` / `openai-compatible` 三条路径，失败降级 mock 并如实上报 `degraded` / `effective_provider`。
`.env`：`LLM_PROVIDER=ollama`、`LLM_MODEL=qwen3:1.7b`。

**换模型 = 改一个环境变量 + `ollama pull` 一个新 tag。** 所谓"脱千问"，成本不在代码，在**评测**——你得先能证明换了之后不变差。所以 DS 系列的顺序必须是：**先建评测集 → 再换底座 → 再谈 LoRA**。

---

## 3. 目标架构

```
                    ┌─────────────────────────────────────────┐
   决策层            │ LLM（可替换底座，默认 1.7B 本地）        │
   （大脑）          │ 职责：证据→结构化判断 / 工具调度 / 话术  │
                    │ 约束：只出 JSON，不自由发挥              │
                    └──────────────▲──────────────────────────┘
                                   │ EvidenceEnvelope（统一封套）★新增
                    ┌──────────────┴──────────────────────────┐
   证据契约层        │ app/schemas/evidence_envelope.py         │
   （本方案核心）    │ 见 §3.1                                  │
                    └──────────────▲──────────────────────────┘
                                   │ 各模块原生输出（已有 17 个 schema）
   ┌───────────┬───────────┬───────┴────┬───────────┬──────────┐
   │ 时序      │ 图/根因    │ 日志/链路   │ 多模态    │ 记忆/RAG │
   │ anomaly   │ rootcause │ log/trace  │ vision    │ memory   │
   │ forecast  │ tgat      │ temporal   │ grounding │ rag      │
   └───────────┴───────────┴────────────┴───────────┴──────────┘
                                   │
                    ┌──────────────▼──────────────────────────┐
   门禁层            │ guard / redlines / robot_guard（三道锁） │
   （已有，不动）    │ recovery_contracts（一本账）             │
                    └─────────────────────────────────────────┘
```

### 3.1 统一证据封套（唯一新增的核心抽象）

现有 `app/schemas/*` 有 17 个 domain schema（anomaly / rootcause / trace / tgat / log / retrieve / adaptive_threshold / forecast / action / orchestrator / reflection / simulator …），各自合理，但 LLM 侧拿到的是 17 种形状。封套只做**归一化，不改各模块语义**：

```python
# app/schemas/evidence_envelope.py（新增）
class EvidenceRef(BaseModel):
    evidence_id: str
    kind: Literal["metric","topology","log","trace","vision","memory","knowledge","rule"]
    module: str              # "anomaly_detector" / "rootcause_detector" / ...
    module_version: str
    captured_at: datetime
    derivation: Literal["observed","derived","inferred"]   # 原 confidence，改名避免与判定 confidence(0-1) 撞名
    # 关键：证据本身的可靠性，不由下游 LLM 重新解释
    quality: Literal["ok","stale","partial","rejected"]
    rejection_reason: str | None = None   # 对齐 recovery-contract 的 reason_codes 风格

class EvidenceEnvelope(BaseModel):
    run_id: str
    subject: str                       # 被观测对象（服务/节点/主机）
    round: int
    refs: list[EvidenceRef]
    # 缺口必须显式：没有证据 ≠ 证据正常
    gaps: list[str]                    # 例：["no_trace_for_order_svc","log_sampling_insufficient"]
    provenance: dict[str, str]
    digest: str                        # canonical JSON SHA-256，对齐 recovery-contract §2.1
```

三条硬规则（直接继承 `semantics.md` 的纪律）：
1. `gaps` 非空时，LLM 侧**不得**输出"恢复/正常"类结论，只能输出"证据不足 + 建议补证"。
2. `quality != "ok"` 的 ref **不得**参与正向判定，只能作为反例来源。
3. 封套 `digest` 一旦签发不可改写；追加证据 = 新 `round` + 新 `digest`。

**与既有 `training/schemas/smartops-training-sample.schema.json` 的映射**（封套不新增语义，只补齐训练侧没有的四件）：

| 封套字段 | 训练侧既有字段 | 规则 |
|---|---|---|
| `evidence_id` | `evidence.evidence_id` | 同名同义，直接沿用 |
| `kind` | `evidence.source`（自由文本） | 收敛成 8 个枚举值 |
| `captured_at` | `evidence.timestamp` | 同义 |
| `quality` | `evidence.evidence_status`（`DIRECT` / `INDIRECT`） | `DIRECT→ok`、`INDIRECT→partial`，另加 `stale` / `rejected` |
| 训练侧无 | `evidence.support_relation`（`SUPPORTED`…） | **不并入封套**：它是判定结果，属于 `evidenceOutput.label`，混进证据会造成"证据自带结论" |
| `module` / `module_version` / `gaps` / `digest` | 无 | 封套新增，训练侧不需要 |

`digest` 必须复用 `agent/recovery_contracts/models.py` 的 `canonical_json` / `object_digest`，**不在 `ai-service` 里另写一份**（否则两套算法必然漂移）。

### 3.2 结构化输出（让 1.7B 可用的前提）

1.7B 的自由生成不可信，但在**受限语法空间**内生成是可靠的。落地方式（三选一，按依赖代价排序）：

| 方案 | 依赖 | 适用 |
|---|---|---|
| Ollama `format: json` + JSON Schema | 零新增依赖 | **首选**，`_ollama_generate` 已在本项目内，加一个参数即可 |
| vLLM / SGLang 的 guided decoding | 换推理后端 | 需要并发时才上 |
| outlines / lm-format-enforcer 本进程约束 | 新增 Python 依赖 | 用 `openai-compatible` 后端时 |

**输出契约固定为单一形状**。注意它必须是既有 `evidenceOutput` 的**超集**，否则 SFT 学到的目标与线上输出不是同一个东西：

| 训练侧 `expected_behavior.evidenceOutput` | 线上输出 | 规则 |
|---|---|---|
| `label`（`SUPPORTED`/`PARTIALLY_SUPPORTED`/`UNSUPPORTED`/`CONTRADICTED`） | `verdict` + `label` | 线上多一档 `INSUFFICIENT`，其余同名同枚举 |
| `reason` | `rationale` | 改名，限 240 字 |
| `supporting_evidence[]` | `used_refs[]` | 引用证据 id |
| `confidence`（0–1） | `confidence` | 训练侧必有，线上不得丢失 |
| 无 | `gaps_acknowledged[]` | 新增 |
| 无 | `next_probe{decision,probe_id,reason}` | 新增 |

**实测落地状态（2026-11-21）**：上表映射已实现且被守卫测试钉住
（`ai-service/app/tests/test_decision_contract.py`，15 条）。真实评测 `EXP-DS04-2026-11-21`
（qwen3:1.7b，n=32）：`json_valid_rate=1.0000`、`hallucination_rate=0.0000`、
`safety_violation_rate=0.0000`；带 schema 的 `pass_rate=0.5000` vs 无 schema `0.4375`（n=32 单次运行，不声明显著性）。

⚠️ **遗留偏差**：「训练侧必有，线上不得丢失」这条**未完全满足**——
`DECISION_SCHEMA.required` 只含 `verdict / used_refs / gaps_acknowledged / next_probe / rationale`，
缺 `label` 与 `confidence`，故带 schema 时模型 32/32 条省略这两个字段。
训练数据仍恒产出它们（`build_distill_dataset.py:258-266`），两侧形状因此不完全同形。
本次未改（改 required 会变更输出分布、使既有对照失效），改为登记 + 加断言锁定现状。
详见 `.trae/documents/DS-04-结构化输出约束验收记录-2026-11-21.md` §1/§6。

```json
{ "verdict": "SUPPORTED|PARTIALLY_SUPPORTED|UNSUPPORTED|CONTRADICTED|INSUFFICIENT",
  "label": "SUPPORTED|PARTIALLY_SUPPORTED|UNSUPPORTED|CONTRADICTED|null",
  "used_refs": ["ev-..."],
  "confidence": 0.0,
  "gaps_acknowledged": ["..."],
  "next_probe": {"decision":"SELECTED|WAIT|STOP","probe_id":"...","reason":"..."},
  "rationale": "≤240字，必须引用 used_refs 中的 id" }
```

`verdict=INSUFFICIENT` 时 `label` 允许为 `null`（训练侧没有这一档，属于线上新增语义）。

`rationale` 里出现 `used_refs` 之外的 id → 判定为幻觉，直接拒绝（可在 `output_guard` 里加这条规则，**不新建体系**）。

---

## 4. 换底座路线

### 4.1 底座候选（全部非千问；许可证需按 MASTER.md 逐条复核）

| 模型 | 规模 | 许可证（**待核验**） | 备注 |
|---|---|---|---|
| `HuggingFaceTB/SmolLM2-1.7B-Instruct` | 1.7B | Apache-2.0 | **首选**：同规模、Ollama 有官方 tag、许可最干净 |
| `TinyLlama/TinyLlama-1.1B-Chat-v1.0` | 1.1B | Apache-2.0 | 最保守兜底，中文弱，需 LoRA 补 |
| `internlm/internlm2_5-1_8b-chat` | 1.8B | 需核（Apache-2.0 口径） | 中文最好，但需确认许可与商用条款 |
| `microsoft/Phi-3.5-mini-instruct` | 3.8B | MIT | 能力强一档，但超出 1.7B 预算 |
| `google/gemma-2-2b-it` | 2B | Gemma Terms（**非 OSI**） | ⚠️ 竞赛可用于展示，商用需读条款 |
| `meta-llama/Llama-3.2-1B-Instruct` | 1B | Llama 3.2 社区许可（**非 OSI**） | ⚠️ 同上 |

**硬门禁（照 MASTER.md 的 Open Source Intake 执行）**：引入前必须 `GET https://api.github.com/repos/...` 或 HF API 拉 `license` 字段，把 SPDX id + 核验日期写进 `reports/open-source-license-verification-<date>.md`。**星数和"大家都在用"永远不构成商用依据。** 底座还须额外记录 `qwen_dependency`（判定见 §6 准入规则）：依赖 Qwen 权重或 DashScope 的候选，即便许可证干净也不进主干。

### 4.2 分步（顺序不可颠倒）

```
① 建 LLM 评测集（30-50 条金标，覆盖：正常判定 / 反例 / 证据不足 / 越权动作拦截）
        ↓  没有它，后面全部无法验收
② 录基线：qwen3:1.7b 在当前证据封套上的分数（准确率 / 幻觉率 / 平均工具调用数）
        ↓
③ 换底座（改 LLM_MODEL），跑同一评测集 → 得到「不退化」证据或否决该底座
        ↓
④ 若退化可接受 → 用 219 条种子做教师扩样 → LoRA → 再跑评测集
        ↓
⑤ 通过 → 写进 reports/；不通过 → 回滚 LLM_MODEL，保留评测集（它本身就有资产价值）
```

**关键判据**：③ 之后如果分数掉超过 10 个百分点，**不要急着 LoRA**——先改结构化输出约束，因为 1.7B 的损失大多来自格式失控，不是知识不足。

---

## 5. 蒸馏管道（正确的形态）

**落点（2026-11-18 修订）**：`scripts/`（与 `build_sft_dataset.py` 同侧）+ `data/training/{candidates,verification}/`。**不新建 `ai-service/distill/`**——那会把训练数据管道切成两半，prompt 对齐与金标排除逻辑都得抄一遍。

**样本格式**：必须通过 `training/schemas/smartops-training-sample.schema.json` 校验，`task_type="EVIDENCE_VERIFICATION"`，判定写在 `expected_behavior.evidenceOutput`。现有 732 条 QA 与 40 条 candidates **都不能**直接当训练样本：前者缺证据包，后者缺 `expected_behavior`。

```
知识语料 217 段（+ 219 条知识样本，若有）
   │  ← 领域知识只进 RAG，不进权重
   ▼
任务化改写：语料 + candidates 的真实 evidence[] →「证据包 → evidenceOutput」成对样本
   │  教师模型：本地大模型优先（合规），外部 API 需留条款摘录
   ▼
质量筛（三遍，逐条写进 data/training/verification/rejects.jsonl）
   ① SCHEMA_INVALID：不通过 smartops-training-sample.schema.json
   ② VERDICT_UNSTABLE：同输入 3 次采样 label 不一致 → 丢弃或降级标 inferred
   ③ REF_HALLUCINATED：supporting_evidence 引用了输入 evidence[] 中不存在的 id
   ▼
数据集（3k–10k 条）→ LoRA（rank 16-32，仅训 attention 投影层）
   ▼
评测集回归（DS-02 同一套金标）→ 通过才发版
```

**为什么这套能工作**：教师生成的是**任务格式与判读口径**，学生学的是"给定这堆证据，该吐什么"。219 条种子决定了任务的**形状**，教师负责把形状铺满。这跟你想要的"蒸馏别人的模型"是同一件事的正确版本。

---

## 6. 开源框架清单（可直接查，许可证待逐条核验）

**准入规则（2026-11-18 增补，与许可证门禁并列）**：本方案的前提是「脱千问」，所以引入项必须先判生态依赖，再判许可证。

| `qwen_dependency` | 判定 | 处置 |
|---|---|---|
| `none` | 默认推理链路不依赖 Qwen 家族权重、DashScope API 或 Qwen 专用 tokenizer | 正常按许可证评估 |
| `optional` | 提供了 Qwen 适配，但可切到其他底座（如统一走 HF `AutoModel` 接口） | 可用，但 `reports/` 必须写明替代路径与实际生效的底座 |
| `required` | 默认链路写死 Qwen 权重 / DashScope API / Qwen tokenizer | 一律记「仅隔离使用」，**不得进主干** |

判定只认仓库代码与配置文件里的实际依赖，不认 README 的宣称；取不到证据就写「未核验」，不得默认按 `none` 处理。

### 6.1 蒸馏与数据（这一层最缺）

| 框架 | 用途 | 许可证（待核验） |
|---|---|---|
| [argilla-io/distilabel](https://github.com/argilla-io/distilabel) | **合成数据与蒸馏管道编排**，直接对应本方案 §5 | Apache-2.0 |
| [argilla-io/argilla](https://github.com/argilla-io/argilla) | 人工复核与数据策展 UI，适合做 §5 的"质量筛"第三关 | Apache-2.0 |
| [NVIDIA-NeMo/Curator](https://github.com/NVIDIA-NeMo/Curator) | 大规模语料清洗去重 | Apache-2.0 |
| [modelscope/data-juicer](https://github.com/modelscope/data-juicer) | 中文语料处理算子库 | Apache-2.0 |
| [HumanSignal/label-studio](https://github.com/HumanSignal/label-studio) | 标注平台 | Apache-2.0 |

### 6.2 训练与推理

| 框架 | 用途 | 许可证（待核验） |
|---|---|---|
| [hiyouga/LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory) | 统一 SFT/LoRA/DPO，**本方案 LoRA 首选** | Apache-2.0 |
| [huggingface/peft](https://github.com/huggingface/peft) | LoRA 底层 | Apache-2.0 |
| [huggingface/trl](https://github.com/huggingface/trl) | DPO/PPO（对齐你已有的 `rl_policy.py`） | Apache-2.0 |
| [unslothai/unsloth](https://github.com/unslothai/unsloth) | 单卡快速 LoRA | Apache-2.0 |
| [axolotl-ai-cloud/axolotl](https://github.com/axolotl-ai-cloud/axolotl) | 配置化训练 | Apache-2.0 |
| [vllm-project/vllm](https://github.com/vllm-project/vllm) | 高并发推理 + guided decoding | Apache-2.0 |
| [sgl-project/sglang](https://github.com/sgl-project/sglang) | 同上，结构化输出更强 | Apache-2.0 |

### 6.3 结构化输出与护栏（补 §3.2 的缺口）

| 框架 | 用途 | 许可证（待核验） |
|---|---|---|
| [dottxt-ai/outlines](https://github.com/dottxt-ai/outlines) | JSON Schema 约束解码 | Apache-2.0 |
| [guidance-ai/guidance](https://github.com/guidance-ai/guidance) | 模板化受控生成 | MIT |
| [noamgat/lm-format-enforcer](https://github.com/noamgat/lm-format-enforcer) | 同上，轻量 | MIT |
| [guardrails-ai/guardrails](https://github.com/guardrails-ai/guardrails) | 输出结构/内容校验（**接你现有 `output_guard.py`**） | Apache-2.0 |
| [NVIDIA/NeMo-Guardrails](https://github.com/NVIDIA/NeMo-Guardrails) | 对话级策略（可对应"三道锁"的外层） | Apache-2.0 |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | 把"提示词工程"变成可优化程序 | MIT |

### 6.4 服务化与工程

| 框架 | 用途 | 许可证（待核验） |
|---|---|---|
| [bentoml/BentoML](https://github.com/bentoml/BentoML) | 把 27 个 service 打包成统一推理服务 | Apache-2.0 |
| [triton-inference-server/server](https://github.com/triton-inference-server/server) | 多框架统一推理 | BSD-3-Clause |
| [kserve/kserve](https://github.com/kserve/kserve) | K8s 推理网关 | Apache-2.0 |
| [mlflow/mlflow](https://github.com/mlflow/mlflow) | 模型注册与实验追踪（**接 `training_ledger.py`**） | Apache-2.0 |
| [iterative/dvc](https://github.com/iterative/dvc) | 数据与权重版本化 | Apache-2.0 |
| [feast-dev/feast](https://github.com/feast-dev/feast) | 特征存储（指标特征复用） | Apache-2.0 |

### 6.5 AIOps 领域（对照你已有实现，用于 benchmark 而非替换）

| 框架 | 用途 | 许可证（待核验） |
|---|---|---|
| [salesforce/Merlion](https://github.com/salesforce/Merlion) | 时序异常检测基线库（对照 `anomaly_detector`） | Apache-2.0 |
| [online-ml/river](https://github.com/online-ml/river) | 在线学习 / 漂移检测 | Apache-2.0 |
| [chaos-mesh/chaos-mesh](https://github.com/chaos-mesh/chaos-mesh) | 故障注入，造评测集用的真实故障 | Apache-2.0 |
| [chaosblade-io/chaosblade](https://github.com/chaosblade-io/chaosblade) | 同上，更轻 | Apache-2.0 |

> **重要**：以上 20+ 个仓库名来自公开检索，**许可证一栏是待核验项**，不是我担保的事实。落地前必须按 MASTER.md 用 GitHub/HF API 复核并把 SPDX id 写进 `reports/`。这也是 DS-07 任务的内容。

---

## 7. 与「三道锁 + 一本账」的映射（不改既有体系）

| 既有机制 | 本方案怎么接 | 不许做什么 |
|---|---|---|
| `agent/security_baseline/redlines.py` | 1.7B 输出的 `next_probe` 决策先过 redlines 再执行 | 不许在 LLM 侧绕过红线判断 |
| `ai-service/app/guard/output_guard.py` | 新增一条规则：`rationale` 引用不存在的 ref id = 幻觉，拒绝 | 不许新建第二套 guard |
| `agent/safety/approval.py` | 高危动作仍走人工审批 | 不许因为"模型换了"就放宽审批 |
| `agent/recovery_contracts/*` | 封套 `digest` 与 `VerificationReceipt.evidence_snapshot_digest` 同规则 | 不许两边算法不一致 |
| `scripts/training_ledger.py` | LoRA 训练记录写进同一本账 | 不许另开训练账本 |

---

## 8. 验收

| 编号 | 判据 |
|---|---|
| D1 | `EvidenceEnvelope` 单测：`gaps` 非空时，LLM 侧必须返回 `INSUFFICIENT`（构造用例断言） |
| D2 | 封套 `digest` 与 recovery-contract canonical JSON 规则逐字节一致（同一输入的 digest 相等） |
| D3 | LLM 评测集 ≥30 条，四类各 ≥5 条；每条的通过判据可机判 |
| D4 | 基线分数写进 `data/training/eval/baseline-report.json` 的 14 项指标（不另造字段），`status` 从 `NOT RUN` 变为 `RUN` |
| D5 | 换底座后同评测集分数差 ≤10 个百分点，或给出否决理由 |
| D6 | 结构化输出：JSON schema 通过率 ≥98%；`rationale` 幻觉引用率 ≤2%；且输出契约是 `evidenceOutput` 的超集 |
| D7 | LoRA 数据集可复现：种子来源 + 教师配置 + 筛除率全记录；每条样本通过 `smartops-training-sample.schema.json` |
| D8 | 所有引入的开源框架：SPDX id + `qwen_dependency`（含依赖证据）+ 核验日期 + 仓库 URL 写入 `reports/open-source-license-verification-<date>.md` |
| D9 | 回滚：改回 `LLM_MODEL=qwen3:1.7b` 后服务正常，且评测集可重跑 |

---

## 9. 未决问题（不假装解决）

1. **B 站视频内容未取得**。`https://www.bilibili.com/video/BV1GQpn6BEHy` 的页面元信息与字幕未能取回，无法确认它演示的具体功能。本方案按你贴的文字清单设计，**不是对那个视频的还原**。若需要对齐，给标题/截图/要点即可。
2. **各感知模块的真实能力未知**。本方案只确认文件存在，未跑 `bench_*`。第 1.1 表里的 ✅ 表示"有实现"，不表示"指标达标"。
3. **教师模型的训练条款未核**。DS-03 必须先产出条款摘录，否则扩样管道不启动。
4. **1.7B 中文能力**。SmolLM2 中文弱是已知事实；若评测显示中文话术不可接受，退路是 `internlm2_5-1_8b`（需先核许可）或保留"模板化话术 + 模型只出结构化字段"。
5. **219 条样本的构成未知**。若这 219 条是知识条目而非任务样本，扩样前必须先做任务化改写（DS-04 的第一步），不能直接当 SFT 数据。**2026-11-18 复核补充**：仓库里现有的是 217 个语料段落产出的 732 条知识型 QA，性质与"知识条目"一致，因此任务化改写这一步确定要做。

---

## 10. 一句话总结

你不需要更多神经网络，也不需要用语料去"替换"一个模型。
你需要的是：**让已有的 20 多个感知模块说同一种话（证据封套），让 1.7B 只在受限语法里说话（结构化输出），然后用 219 条种子把"该怎么说"蒸馏进一个可商用的底座里。**

这三件事做完，"脱千问"就是一次配置变更加一份评测报告。
