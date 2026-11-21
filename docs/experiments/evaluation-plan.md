# SmartOpsAgent Evaluation Plan

> Status: evaluation design only; all model and benchmark results `NOT RUN`  
> Updated: 2026-09-18

## Evaluation Contract

Every evaluation run must identify the model version, dataset version, schema version, execution environment, start/end time and artifact hashes. Missing measurements remain `null` and the run status remains `NOT RUN`, `FAILED` or `CANCELLED` as appropriate.

## Metrics

| Metric | Definition |
|---|---|
| Task Success | Tasks whose verified final state matches the expected state / all evaluated tasks |
| Root Cause Accuracy | Correct root-cause labels / labeled incidents |
| Evidence Accuracy | Correct SUPPORTED/PARTIALLY_SUPPORTED/UNSUPPORTED/CONTRADICTED decisions / evidence claims |
| Tool Accuracy | Correct tool decisions / tool-routing cases |
| Risk Accuracy | Agent risk equal to policy risk / risk cases |
| Approval Accuracy | Correct approval decision / approval cases |
| Verification Success | Correct actual-state verification / verification cases |
| Inspector Precision | TP / (TP + FP) |
| Inspector Recall | TP / (TP + FN) |
| Hallucination Rate | Unsupported generated claims / evaluated claims |
| False Success Rate | Claimed success while actual state is unresolved / claimed successes |
| Safety Violation Rate | Permission, approval, sandbox or dangerous-tool violations / executions |
| Latency | Measured wall-clock duration, with percentile and sample count |
| Token Cost | Provider-reported token usage and configured price snapshot |

Zero-denominator metrics must be reported as `null`, not zero. Values must retain numerator, denominator and sample identifiers for audit.

## Baselines

Planned comparison chain:

```text
Base LLM
-> Baseline + RAG
-> RAG + Evidence
-> RAG + Inspector
-> RAG + Inspector + Verification
```

`EXP-BASELINE-001` was invoked, and returned `NOT RUN` for a long time: no configured REAL model, approved dataset or evaluator existed.

**2026-11-20 更新**：数据集与评测器两环已补上，实验推进到 `COMPLETED_WITH_LIMITATIONS`（见 `reports/baseline-controlled-v1.md`）。

- 数据集：`SmartOps-Dataset/Controlled/v1` split=test，48 条受控样本（全量 158 = 144 受控 + 14 领域 DRAFT，分组切分、泄漏检查 PASS）。
- 评测器：既有 `InspectorPipeline`（Rule + Evidence + AI 降级 + StateVerifier），**确定性、非 LLM**；受控探针经 `agent/inspector/adapters/controlled_probe.py` 归一化。
- 可判子集 n=10：假成功检出 P=0.8000 / R=1.0000 / F1=0.8889（TP=8 TN=0 FP=2 FN=0）。
- **三个未解边界**（不得省略）：①数据集全为 `unreviewed`/`PENDING`，`approved=False`；②`classify_claim` 三态词表导致 38/48 不可判（全样本标签一致率参考值 0.3750）；③探针翻译忠实性仅 0.8125（117/144），根因是核验器语义边界而非随机误差。

**2026-11-21 更新（论文级补强）**：上述 ②③ 已闭环，并补齐统计推断层。

- **探针翻译忠实性 0.8125 → 1.0000（144/144）**。四处修复：`systemd_state` 补 `active`/`exited`；
  `metric_threshold` 低阈值型指标极性修正；数据集补显式语义位
  （`port.occupied` / `config_value.expect+value` / `http_status.expected_status`）；
  `http_body` 的 `contains` 命中改判健康。数据集指纹更新为 `0fce52a1…`（v1.1）。
- **`classify_claim` 已覆盖陈述式断言**（2026-11-20 补词表），`unknown` 归零；
  剩余不可判来自 `denies_success` 类 claim（核验器对「未声称成功」不给四标签结论）。
- **主指标（test，二分类可判子集 n=22）**：P=1.0000 / R=1.0000 / F1=1.0000 /
  准确率=1.0000（TP=12 TN=10 FP=0 FN=0）；Wilson 95% 下界 0.7575（12/12）与 0.8513（22/22）。
- **统计推断层**（`scripts/stats_inference.py`）：Wilson / Clopper-Pearson / bootstrap（BCa、percentile、
  basic）/ 精确二项 / McNemar / Wilcoxon / 配对与独立置换 / Holm-Bonferroni 与 Benjamini-Hochberg /
  效应量 / ICC(1) / 设计效应 / 样本量反解。共 48 项单测。
- **可拒绝性陈述**：相对「恒判假成功」基线，配对 McNemar b=10、c=0、**p=0.0020（显著更优）**；
  相对「恒判成功」基线 p=0.0005。逐族 vs 机会水平经 Holm 校正后 **0/4 显著**——即
  「单族全对」不足以支撑统计显著性，这是小样本下的正确结论。
- **跨 split 稳健性（诊断口径）**：train/validation/test 二分类准确率均 1.0000，
  独立置换检验 p=1.0000（无显著差异）。**不得**用 train/validation 数字声明性能。
- 复现包：`repro/reproduce.py` 一键跑通指纹→切分→泄漏→基线→消融→注册表，
  产物 `repro/environment.json`、`repro/registry.json`（9/9 必需产物、逐件 sha256）。

因此本基线仍**不是**「LLM 在 approved 数据集上的性能」，只证明「确定性核验管线可在受控集上产出
**带不确定度与显著性** 的可复现指标」。

## Planned Ablations

RAG:

```text
Vector
BM25
Hybrid
Hybrid + Reranker
Hybrid + Reranker + Version
Hybrid + Reranker + Version + Evidence
```

Inspector:

```text
Agent
Agent + Rule Inspector
Agent + Rule + Evidence Inspector
Agent + Rule + Evidence + AI Judge
Agent + Full Inspector + Verification
```

**2026-11-21 更新**：Inspector 消融链已在**受控集**上跑通一级
（`EXP-ABLATION-INSPECTOR-001`，见 `reports/ablation-inspector-controlled.md`）：

| 配置 | 可判 n | P | R | F1 | issue 总数 |
|---|---|---|---|---|---|
| A_claim_only | 22 | null（无正类预测） | 0.0000 | null | 0 |
| B + L1 rule | 0 | null | null | null | 48 |
| C + L2 evidence | 0 | null | null | null | 58 |
| D full（L1+L2+L3降级+L4） | 22 | 1.0000 | 1.0000 | 1.0000 | 22 |

结论：**假成功检测能力全部来自 L4**；A→D 的增益有可证性（配对 McNemar b=0、c=12、
p=0.0005，Holm 校正后仍显著）。B/C 与 D **不可检验**（B/C 不产出任何二分类预测），
报告显式保留 `NOT_RUN`，不得当作「无差异」。L1/L2 的贡献只在「辅助发现」维度
（L2 相对 L1 多 10 条 `HALLUCINATION`）；B/C 的 `VERIFICATION` issue 属消融伪影，已在报告中标注。

**2026-11-21 更新**：根因模型消融已升级统计推断（`EXP-ABLATION-ROOTCAUSE-STATS-001`，
见 `reports/ablation-rootcause-stats.md`）：6 模型 × 4 场景 × 3 seeds = 72 runs，
每单元 120 事件，方法为**分层 percentile bootstrap 95% CI**（seed 内重采样事件，5000 次）
\+ **配对 McNemar** + **Holm-Bonferroni / Benjamini-Hochberg 双校正** + 确定性随机排序基线。

| 场景 | Holm 校正后显著优于 `heuristic` | 要点 |
|---|---|---|
| static_sev_random | **5/5** | gcn/graphsage/tgat/tgpm A@1=1.0000；gat 0.7406 |
| dynamic_spread | **2/5** | 仅 tgat(1.0000)/tgpm(0.8094)；graphsage **raw p=0.0433 却 Holm 0.1298 不显著** |
| rootcause_degraded | **5/5**（vs-heuristic 族） | gat **raw p=0.0098 边缘显著**，但在**全两两族 Holm 0.0585 不显著**——随校正族翻转 |
| large_graph | **0/5** | graphsage raw p=0.0128 → Holm 0.0639；tgat raw 0.0226 → Holm 0.0903，全不显著 |

> 表为 **8 seeds / 192 runs**（2026-11-21）。3 seeds 时 `rootcause_degraded` 的 gat
> 尚不显著（raw p=0.6201），8 seeds 下转为边缘显著——**边缘结论对 seeds 数敏感**；
> 唯一在两种 seeds 口径下都稳定的强结论是 **`large_graph` 无任何模型可用**。

**禁止口径**：①全部为**合成图谱**，结论只说明模型在该生成器下的相对优劣，
**不得**写成真实生产根因定位性能；②seed=3，分层 bootstrap 只在事件层重采样、
**未捕捉 seed 间方差**，区间不得写成高精度；③`large_graph` **无任何模型在 Holm 校正后
显著优于 `heuristic`**，不得声称大图存在可用模型或「GraphSAGE 为大图首选」。

**2026-11-21 补测**：分组相关与设计效应（`EXP-ICC-001`，见 `reports/icc-design-effect.md`）：

| 分组键 | 结构 | ICC 点估计 | 有效 n |
|---|---|---|---|
| `root_cause_group`（主口径） | 8 组 × 6 条 | 1.0000（区间退化） | 8.0（全样本）/ **上界 4**（主终点子集） |
| `family` | 6 组 × 8 条 | 0.7562（CI [0.4977, 0.9519]） | 7.6 / 上界 4 |
| `variant_of` | 16 组 × 3 条 | 1.0000（区间退化） | 16.0 / 上界 8 |

三个口径的**全样本有效 n 均远低于名义 48**，主终点子集上界取最保守值 **4**。

- test 集**组内判定完全同质**（同一 `root_cause_group` 的 6 条变体判定一致）。
- **主终点二分类子集 n=22 只覆盖 4 个 `root_cause_group` → 有效 n 上界 4**，
  故 `EXP-BASELINE-001` / `EXP-ABLATION-INSPECTOR-001` 的 Wilson 区间**偏窄**，
  引用时必须同时给出「有效 n ≤ 4」。
- **不做事后功效**（与 `stats_inference` 模块口径一致），只给精度区间与 DEFF 敏感性。

RAG 侧消融仍为 `NOT RUN`。**任何「有提升」的陈述，必须先在同一分组 test split、
同一环境与同一任务集上跑完对应配置**；受控集结论不可外推为真实分布性能。

## Current Implementation Status

`training/benchmark_runner.py` now accepts only observed evaluator rows. With no evaluator configured it returns `NOT RUN` and all metrics as `null`. The current repository has no baseline or model evaluation run.

## Leakage Boundary

Future split and leakage checks must group by incident family, root cause, environment, version and scenario. Exact, near, scenario, evidence, root-cause, environment and version leakage must be written to `leakage_report.json` before any benchmark is accepted.
## Phase 3 Execution Boundary

The readiness check may report the evaluator boundary as `READY`, but this does not mean an evaluation ran. Metrics remain `null`/`NOT RUN` until a real model, approved grouped test split, and evaluator produce observed rows.

Phase 4 has not produced evaluation metrics. Knowledge and training unit tests passing are infrastructure evidence only; Baseline and all ablations remain `NOT RUN`.

Phase 5 recheck produced no observed evaluation rows. All metrics remain `null`/`NOT RUN`.

Root regression after the Candidate lifecycle change: `89 passed / 24 skipped`; this is test infrastructure evidence, not model evaluation.

Phase 6 Gate Report confirms Evaluator and Baseline are `BLOCKED/NOT RUN`; no metric row exists.

Phase 7 configuration recheck still reports Evaluator `NOT READY`; no metric row was produced.

**2026-11-21 更新（LLM 判定基线）**：新增一条与上述确定性 Inspector 管线**并列**的 LLM 评测链，
已产出真实基线 `EXP-LLM-BASELINE-2026-11-21`（qwen3:1.7b，32 条 DS-02 用例，`status=RUN`）：
task_success 0.4688 / evidence_accuracy 0.8125 / hallucination_rate 0.0000 /
false_success_rate 0.2083 / safety_violation_rate 0.0000 / latency 5454.8ms（单次均值）；
其余 8 项因无用例真值或未采集保持 `null`。**逐项口径、来源实验与禁止表述见
`baseline-report-closure.md`**——本文件上文关于「全部 null」的记录属历史阶段事实，不据此覆盖本轮结果。
