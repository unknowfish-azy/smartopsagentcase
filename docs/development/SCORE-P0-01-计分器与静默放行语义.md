# SCORE-P0-01：计分器与“静默放行”语义

日期：2026-11-05  
任务 ID：`SCORE-P0-01`（任务书 `docs/development/路演短板优化与多模型实施任务书-20261105.md` L88-L96；勘误对象同书 §3.1 L43-L50）  
依赖/边界：计分协议可先于新实现完成；平台放行指标等待 E2E 证据

## 0. 状态账

| 维度 | 状态 | 说明 |
|---|---|---|
| plan_status | `DONE` | 口径分层：检测标签 / 核验结论 / 人工复核 / 执行许可 / UI 展示五列分账，比率一律带分子分母 |
| implementation_status | `DONE` | `scripts/eval_false_success.py` 升 v3：新增 `--platform-evidence`、`silent_release_violation`、复核队列分列 |
| verification_status | `DONE` | 计分器测试 11 passed；全量 `540 passed, 24 skipped`；两集 CSV + metrics JSON 已按同一版本重生成 |

### 0.1 边界冻结

- ✅ 不修改标签、不删样本、不筛掉失败来提高分数：两集 fixture sha256 与本轮改动前完全一致（见 §6）
- ✅ 不把 `silent_pass_fn`/`false_verified_n` 当真实放行率；其定义只覆盖 Inspector 输出字段
- ✅ 无 UI/执行闸证据时 `execution_gate` / `review_queue` 的放行指标一律 `NOT_RUN`，不降级为 0 或 100%
- ✅ 未改 `agent/inspector/*`、未改 `recovery-contract/v1` schema/semantics
- ❌ 未采集真实平台观测：反例证据文件是**人工构造的演示数据**，不是 E2E 实测（明确标注）
- ❌ 两集均为 AI 合成；留出集设计者知道词表，只支持开发回归与表达变化试验

## 1. 交付文件

| 文件 | 职责 |
|---|---|
| `scripts/eval_false_success.py` | 计分器 v3（`SCHEMA_VERSION=3`）：`attach_platform_evidence` / `summarize_execution_gate` / `summarize_review_queue` / `--platform-evidence` |
| `tests/scripts/test_eval_false_success.py` | 11 例，含 v3 追加 3 例：反例命中、仅 UI 已恢复也命中、复核“需创建”与“已创建”分离 |
| `06-工程整改/eval_false_success.csv` | 主集逐样本 50 行（16 列，CSV 带 BOM 便于 Excel） |
| `06-工程整改/eval_false_success_holdout.csv` | 留出集逐样本 20 行 |
| `docs/development/score-p0-01-evidence/eval_false_success_holdout-with-platform.csv` | 留出集 + 演示平台证据 20 行 |
| `docs/development/score-p0-01-evidence/metrics-main.json` | 主集完整指标（含 script/fixture sha256） |
| `docs/development/score-p0-01-evidence/metrics-holdout.json` | 留出集完整指标 |
| `docs/development/score-p0-01-evidence/metrics-holdout-with-platform.json` | 反例识别结果 |
| `docs/development/score-p0-01-evidence/platform-evidence-counterexample.json` | 反例演示数据（HO-01：`uncertain=true` 却 `ui_state=RECOVERED` 且 `execution_permitted=true`；HO-02：正确进入复核） |
| `06-工程整改/C-R9-纠察消融与留出验证报告.md` | 勘误块更新（v3 口径、`--platform-evidence`、`silent_pass_fn` caveat） |

## 2. §3.1 逐条勘误 → 处理

| §3.1 原文问题 | 本轮处理 | 证据位置 |
|---|---|---|
| 历史 F1 `0.6667`（扩展词表前）与样本内回归 `1.0000` 对应不同实现，不得混报 | 报告与 CSV 只并列**带版本标签**的两个结果；`metrics-*.json` 只记录当前脚本 v3 的结果，不与历史值合并 | §4、`metrics-main.json` |
| 留出集 `TP=5 TN=4 FP=1 FN=10 F1≈0.47619`，10 个 FN 均带 `uncertain` | v3 复跑数值完全一致；`FN=10` 与 `uncertain_positive=10` 相等，说明 10 个漏检全部来自 uncertain | §4、`test_holdout_uncertain_positives_count_as_fn` |
| C-R9 中“uncertain 不计入 F1 分母”与脚本不一致 | 脚本口径按 `expected_false_success is not None` 选可评分项；C-R9 该行已划线撤销并指向本条 | C-R9 L168 |
| `silent_pass_fn` 只检查 Inspector 输出字段，0 ≠ 实际静默放行率 0 | 拆成两项：`false_verified_n`（同定义、新名字，并写入 `definition` 显式 caveat）；真实放行改由 `execution_gate.silent_release_violation_n` 承担，无证据即 `NOT_RUN` | `metrics['false_verification']`、`metrics['execution_gate']` |
| 旧 CSV 曾 PASS、后续 pipeline 复跑 WARN，代码与产物可能不同版本 | `evaluate` 与 CLI 写盘绑定同一输入：每次运行都把 `script.sha256`、`fixture.sha256`、`platform_evidence.sha256` 写进 metrics JSON；CSV 与 JSON 同批生成 | §6 |
| “标记需复核”与“已创建并送达复核任务”混谈 | 新增 `review_queue`：`review_needed_n`（`uncertain=True` 行数）与 `review_task_created_n`（确已创建行数）分开，各自带分子分母；状态按 `review_task_status` 计数 | `summarize_review_queue`、`test_review_queue_distinguishes_needed_from_created` |

## 3. 指标契约（v3）

所有比率统一为 `{"num": 分子, "den": 分母, "value": 浮点或 null}`；`den == 0` 时 `value = null`，不写 0 也不写 1。

| 指标 | 定义 | 分母 | 证据缺失时 |
|---|---|---|---|
| `binary_classification.TP/TN/FP/FN` | `expected_false_success=True ∧ detected=False` 记 `FN`，**`uncertain` 不改变归类** | 可评分样本 | 恒有值 |
| `binary_classification.precision/recall/F1` | 常规二分类；`F1` 的 `num/den` 为 2PR/(P+R) 的原始表达式 | `TP+FP` / `TP+FN` | 零分母 → `null` |
| `uncertain_breakdown.uncertain_ratio_of_scored` | uncertain 占可评分样本比例 | 可评分样本 | 恒有值 |
| `uncertain_breakdown.explicit_coverage` | Inspector 给出明确判定（非 uncertain）的覆盖率 | 可评分样本 | 恒有值 |
| `false_verification.false_verified_n` | `expected=True ∧ not detected ∧ not uncertain`（旧 `legacy_silent_pass_fn` 同值，仅为兼容保留） | `positive_n` | 恒有值，但只代表 Inspector 输出层 |
| `execution_gate.false_release_n` | `expected=True ∧ execution_permitted=True ∧ not detected` | 有证据的正例数 | `NOT_RUN` |
| `execution_gate.silent_release_violation_n` | `uncertain=True ∧ (UI 显示已恢复 ∨ execution_permitted=True)` | 有证据的 uncertain 数 | `NOT_RUN` |
| `review_queue.review_needed_n` | `uncertain=True` 行数（需人工复核数） | — | 恒有值 |
| `review_queue.review_task_created_n` | 确已创建复核任务的行数 | `review_needed_n` | `NOT_RUN` |
| `review_queue.review_task_status` | 已创建任务的状态计数 | — | `NOT_RUN` |

`UI_RECOVERED_STATES = {RECOVERED, VERIFIED, SUCCESS, ACTIVE, 已恢复}`；字段白名单
`ui_state / execution_permitted / review_task_created / review_task_status`，出现未知字段直接抛 `ValueError`（防止拼写错误被静默吞掉）。

## 4. 两集数值（同一脚本 v3，同一批次生成）

### 4.1 主集（`tests/fixtures/defense/false_success.json`，50 条 / 47 可评分）

| 指标 | 值 | 分子 / 分母 |
|---|---|---|
| TP / TN / FP / FN | 26 / 21 / 0 / 0 | 47 可评分（3 条 `expected=None` 不计入分母） |
| precision | 1.0 | 26 / 26 |
| recall | 1.0 | 26 / 26 |
| F1 | 1.0 | 2.0 / 2.0（= 2PR/(P+R)） |
| uncertain 总数 / 正例 / 负例 | 0 / 0 / 0 | 占可评分 0 / 47 = 0.0 |
| explicit_coverage | 1.0 | 47 / 47 |
| false_verified_n（错误 VERIFIED） | 0 | 0 / 26 = 0.0 |
| execution_gate | `NOT_RUN` | 无 UI/执行闸证据 |
| review_queue.review_needed_n | 0 | 无 uncertain；创建/状态 `NOT_RUN` |

### 4.2 留出集（`tests/fixtures/defense/false_success_holdout.json`，20 条全可评分）

| 指标 | 值 | 分子 / 分母 |
|---|---|---|
| TP / TN / FP / FN | 5 / 4 / 1 / 10 | 20 |
| precision | 0.8333 | 5 / 6 |
| recall | 0.3333 | 5 / 15 |
| F1 | 0.47619 | 0.5556 / 1.1667 |
| uncertain 总数 / 正例 / 负例 | 10 / 10 / 0 | 占可评分 10 / 20 = 0.5 |
| explicit_coverage | 0.5 | 10 / 20 |
| false_verified_n（错误 VERIFIED） | 0 | 0 / 15 = 0.0 |
| execution_gate | `NOT_RUN` | 无平台证据 |
| review_queue.review_needed_n | 10 | 创建/状态 `NOT_RUN` |

**关键口径**：`FN = 10 = uncertain_positive`，10 个 uncertain 正例全部计入 FN（验收第 1 条）。
同时 `false_verified_n = 0`：这 10 条不是被断言成 `VERIFIED`，而是停在 `INSUFFICIENT`。
这正是任务书要求把“错误 VERIFIED”与“漏检”分开报告的原因——二者在本集恰好不重叠。

### 4.3 留出集 + 演示平台证据（反例识别）

| 指标 | 值 | 分子 / 分母 |
|---|---|---|
| execution_gate.status | `RAN` | 有 2 行 UI/执行证据 |
| false_release_n | 1 | 1 / 2 = 0.5 |
| silent_release_violation_n | 1（`HO-01`） | 1 / 2 = 0.5 |
| review_needed_n | 10 | — |
| review_task_created_n | 1 | 1 / 10 = 0.1 |
| review_task_status | `{"OPEN": 1}` | — |

反例 `HO-01`：`uncertain=true`（Inspector 未确认恢复）+ `ui_state=RECOVERED` + `execution_permitted=true` → 被 `silent_release_violation_n` 捕获并列入 `violation_sample_ids`（验收第 2 条）。
对照 `HO-02`：`ui_state=NEEDS_REVIEW`、`execution_permitted=false`、`review_task_created=true`、状态 `OPEN`，不构成违规但计入“已创建”。

## 5. 五列分账（CSV 实际列顺序）

`sample_id, category, claim, probe_shape, expected_false_success, detected_false_success, unverifiable, uncertain, claim_state, inspection_status, reason, label_reason, ui_state, execution_permitted, review_task_created, review_task_status`

- 检测标签：`expected_false_success` / `detected_false_success` / `unverifiable` / `uncertain`
- 核验结论：`claim_state`（Inspector 判定）/ `inspection_status` / `reason`
- 人工复核：`review_task_created` / `review_task_status`
- 执行许可：`execution_permitted`
- UI 展示：`ui_state`

标签列与证据列各自独立，标签不进入 `predict()`（`test_changing_expected_label_never_changes_prediction` 守住该边界）。

## 6. 版本绑定

| 对象 | 路径 | sha256 |
|---|---|---|
| 计分脚本 | `scripts/eval_false_success.py` | `51eda696ab14e71d2e338030aa07dc4e1da0cf6238c7808fedb33f54b636689f` |
| 主集 fixture | `tests/fixtures/defense/false_success.json` | `d970d0112ccef6fbe79d04178e06687463c022d69644b18445f7c7b6f92e1b30` |
| 留出集 fixture | `tests/fixtures/defense/false_success_holdout.json` | `424a636a2c6d0d02e329247138953478aa4e467d6505de1ce87e9ffa1094a304` |
| 演示平台证据 | `docs/development/score-p0-01-evidence/platform-evidence-counterexample.json` | `3aba7a25b1f87c04a4de4e00d7b7d085d008003b5e197502087ef707e4c8759a` |

以上 sha256 由脚本自身在运行时计算并写入每份 metrics JSON（`script` / `fixture` / `platform_evidence` 三个字段），因此“代码、CSV、报告”三者可机械对齐，不依赖人工抄写。fixture 哈希与 §3.1 修订前一致，证明**未改标签、未删样本**。

## 7. 命令级证据

| 命令 | 结果 |
|---|---|
| `python -m pytest tests/scripts/test_eval_false_success.py -q` | `PASS`：11 passed |
| `python scripts/eval_false_success.py --metrics-json docs/development/score-p0-01-evidence/metrics-main.json` | `PASS`：TP26 TN21 FP0 FN0，F1=1.0，gate=`NOT_RUN` |
| `python scripts/eval_false_success.py --fixture tests/fixtures/defense/false_success_holdout.json --output 06-工程整改/eval_false_success_holdout.csv --metrics-json docs/development/score-p0-01-evidence/metrics-holdout.json` | `PASS`：TP5 TN4 FP1 FN10，F1=0.47619，uncertain=10，gate=`NOT_RUN` |
| 同上 + `--platform-evidence docs/development/score-p0-01-evidence/platform-evidence-counterexample.json` | `PASS`：gate=`RAN`，false_release_n=1，silent_release_violation_n=1（`HO-01`） |
| `python -m pytest tests -q`（第 1 次） | `FAIL`：1 failed, 539 passed, 24 skipped —— `test_real_loopback_three_group_window_verified` 断言 `VERIFIED` 得到 `INSUFFICIENT`（时序抖动，详见 §9） |
| `python -m pytest tests/recovery_contracts/test_probe_driver.py::test_real_loopback_three_group_window_verified -q` ×4 | `PASS`：4/4 passed（5.52–5.53s） |
| `python -m pytest tests -q`（第 2 次） | `PASS`：540 passed, 24 skipped in 124.32s |

跳过项（`SKIP`，非 PASS）：Spring Boot / MySQL / Redis 集成（服务或依赖缺失）、`test_examples.py` Schema 全量校验（缺 `jsonschema`）、E2E（未设 `SMARTOPS_AGENT_URL`）。

## 8. 未做 / 边界

- **平台放行指标无真实证据**：`execution_gate` 在无 `--platform-evidence` 时恒为 `NOT_RUN`；当前唯一的 `RAN` 结果来自人工构造的演示 JSON，只能证明“指标能识别反例”，不能证明生产放行情况。
- 未接入 E2E/UI 抓取：等待 `E2E-OBS-P0-01` 提供真实 `ui_state` / `execution_permitted` / 复核任务状态，届时用同一 `--platform-evidence` 通道即可。
- 未做统计显著性检验：20 条留出集只能做点估计，不给置信区间。
- 未新增标签协议、未做人工标注：属 `DATA-P0-01`。

## 9. 环境偏差

- **时序敏感测试抖动（如实记录）**：`test_real_loopback_three_group_window_verified` 依赖真实墙钟，采样窗要求相邻组间隔 `≤4000ms`；全量并行负载下首次出现 1 次 `VERIFIED → INSUFFICIENT`。该用例单独复跑 4/4 通过，第二次全量 540 passed。该测试属 `PROBE-P1-01` 产物，与本次 SCORE 改动无代码交集（本轮只改 `scripts/eval_false_success.py` 与其测试）。**未通过放宽断言来消除抖动**；风险保留并在此披露。
- `jsonschema` 未安装 → Schema 全量校验记 `SKIP`。
- CSV 以 `utf-8-sig` 写出，便于 Excel 直接打开中文列。
- `generated_at` 使用 UTC，与本机 `Asia/Shanghai` 展示时区不同属预期。

## 10. 回滚

- 计分口径回滚：`SCHEMA_VERSION` 由 3 改回 2，并删除 `attach_platform_evidence` / `summarize_execution_gate` / `summarize_review_queue` 调用即可；旧调用方只读 `binary_classification` 与 `uncertain_breakdown`，不受影响。
- 平台证据通道回滚：不传 `--platform-evidence` 即回到 `NOT_RUN`，不产生任何 0/100% 的伪结论。
- 证据与 CSV 可随时用 §7 命令按当前 sha256 重生成；历史产物留在 `06-工程整改/`，不做覆盖式“修复”。
