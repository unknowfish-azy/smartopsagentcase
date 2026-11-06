# VER-P0-01：证据义务、恢复判据与有限期回执

日期：2026-11-05  
任务 ID：`VER-P0-01`（任务书 `docs/development/路演短板优化与多模型实施任务书-20261105.md` L98-L110）  
规范来源：`docs/design/recovery-contract-v1/schema.json` + `semantics.md`（由 N01 冻结，本任务只消费）

## 0. 状态账

| 维度 | 状态 | 说明 |
|---|---|---|
| plan_status | `DONE` | 规范已由 N01 冻结；本任务按冻结字段实现，未改 schema、未改既有 run-event |
| implementation_status | `DONE` | 本任务认领范围（读取层 / N02 求值 / N04 窗口 / N04 回执与审计）全部落地 |
| verification_status | `DONE` | 19 条冻结样例 + 局部 125 passed/1 skipped + 全量 441 passed/24 skipped；1 项 Schema 全量校验为 `SKIP`（缺 `jsonschema`），2 个对象 `NOT_STARTED`（属 PROBE-P1-01 / REPLAY-P1-01） |

### 0.1 边界冻结

本次严格遵守：

- ✅ 只消费 `recovery-contract/v1`，不改字段、改名或另建第二套契约
- ✅ 复用既有三态逻辑；`StateVerifier.passed` 原义保留（未被改写、未被当作恢复证据）
- ✅ 未签发任何执行权限，未创建审批，未接入 pipeline
- ❌ 不实现 `ProbeDecision`（属 PROBE-P1-01）与 `ReplayBundle`（属 REPLAY-P1-01）
- ❌ 不解析自然语言“已恢复”（只接受 `claim_type=BUSINESS_RECOVERY` 的结构化 Claim）

## 1. 交付文件

| 文件 | 行数 | 职责 |
|---|---:|---|
| `agent/recovery_contracts/models.py` | 728 | 五个对象的严格读取层；canonical JSON、digest、冻结常量校验 |
| `agent/recovery_contracts/evaluator.py` | 599 | N02 三值求值 + N04 采样窗；纯函数，判定时钟由入参传入 |
| `agent/recovery_contracts/receipts.py` | 288 | N04 回执签发、到期/失效事件、JSONL 审计账本 |
| `agent/recovery_contracts/__init__.py` | 81 | 公开符号导出 |
| `tests/recovery_contracts/test_models.py` | 201 | 摘要、必备字段、冻结常量、三值不变式 |
| `tests/recovery_contracts/test_evaluator.py` | 194 | 资格/三值/窗口/谓词注册表边界 |
| `tests/recovery_contracts/test_examples.py` | 183 | 19 条样例逐条 verdict + 原因码 + 回执状态 |
| `tests/recovery_contracts/test_receipts.py` | 204 | 有效期上界、事件不可改写、审计回读 |
| `tests/recovery_contracts/fixtures/vp01-*.json` | 19 个 | 可执行样例包（见 §3） |

## 2. 任务书判据 → 实现映射

| 任务书要求（L98-L110） | 实现位置 | 可复现证据 |
|---|---|---|
| 契约绑定 scope / target / 期望 revision / 义务 / 来源组 / 采样窗 / 证据 TTL / 总预算 / 有效期 | `RecoveryContract.from_dict`（models.py L362）、`Window`/`Budgets` 冻结常量（L38-L56） | `test_models.py` 契约往返、篡改拒绝、常量拒绝 |
| 义务值为 TRUE/FALSE/UNKNOWN | `ObligationResult`（models.py L588）三条不变式 | `test_true_result_must_not_carry_reason_codes` / `test_unknown_result_must_carry_reason_codes` / `test_result_rejects_unknown_reason_code` |
| 合格业务观测明确失败才是 FALSE | `_observation_value`（evaluator.py L233）、谓词模板（L81-L145） | `negative-passed-but-business-false`、`negative-partial-instance-recovery` |
| 缺失、错目标、旧任务、过期、来源未决通常 UNKNOWN | `_reject_reason`（evaluator.py L196-L231） | `negative-missing-field`、`negative-wrong-target`、`negative-old-binding-revision`、`negative-stale-evidence`、`negative-source-conflict` |
| 连接超时默认采集不足；只有契约把“从该位置可达”作为业务条件才判失败 | `_observation_value` 的 `TIMEOUT` 分支 + `endpoint_reachable` 的 `timeout_is_failure` 参数 | `negative-timeout`（INSUFFICIENT）；`test_evaluator.py` 可达性反例（CONTRADICTED） |
| 有必需 FALSE ⇒ CONTRADICTED；无 FALSE 有 UNKNOWN ⇒ INSUFFICIENT；全满足 ⇒ VERIFIED | `evaluate`（evaluator.py L485） | `test_evaluator.py::test_optional_false_does_not_block_verified` 等 |
| 只有 VERIFIED 签 ACTIVE，其余 NOT_ISSUED | `verify`（receipts.py L73）、`VerificationReceipt`（models.py L647） | `test_receipts.py::test_non_verified_is_not_issued` |
| 到期 / 新反例 / revision 变化追加 EXPIRED / INVALIDATED；历史证据保留 | `InvalidationEvent`、`ReceiptLedger.invalidate/expire_due`（receipts.py L39-L288） | `test_history_is_append_only_and_receipt_record_is_immutable`、`test_invalidated_takes_priority_over_expired` |
| 工具成功、审批批准、Inspector 结果与恢复结论各自保存 | `verify()` 结构上不接受 action / 审批 / Inspector 入参 | 结构约束（无法把三态声明当恢复证据） |
| 采样窗：3 组 A/B、首末 ≥4000ms、相邻 ≤4000ms、组内 skew ≤1250ms、下组 ≥2000ms | `evaluate_window`（evaluator.py L282-L343） | `test_window_reports_groups_for_positive_case`、`test_adjacent_group_gap_over_limit_invalidates_window` |
| 停用新签发能力后仍可读历史审计 | `ReceiptLedger(path=...)` 追加 JSONL + `_load()` | `test_receipts.py::test_history_survives_issuance_being_disabled` |

### 2.1 冻结口径（与 schema 一致，未自行改值）

- 原因码 7 个：`MISSING / STALE / WRONG_TARGET / WRONG_REVISION / CONFLICT / TIMEOUT / MALFORMED`
- 窗口常量：`sample_groups=3`、`min_first_last_gap_ms=4000`、`max_adjacent_gap_ms=4000`、`max_intra_group_skew_ms=1250`、`min_next_group_gap_ms=2000`
- 预算常量：`max_probe_calls=12`、`per_probe_timeout_ms=1000`、`run_deadline_ms=30000`、`evidence_ttl_ms=15000`；`receipt_ttl_ms≥1000` 为参数
- canonical JSON：UTF-8、键按码位升序、无空白、禁 NaN；`digest = sha256:` + 去 `digest` 字段后对象的 canonical 摘要
- `valid_until = min(issued_at + receipt_ttl_ms, 全部必需观测 observed_at + evidence_ttl_ms 的最小值)`

## 3. 样例包（19 条，全部通过）

| # | 用例 | 缺陷 | 期望 verdict | 期望原因码 | 规则 |
|---:|---|---|---|---|---|
| 1 | `positive` | 3 组 A/B、r17、窗口满足 | `VERIFIED` | `[]` | EO-ALL / W-001..W-006 / RS-001 |
| 2 | `negative-stale-evidence` | 证据年龄 36s > 15000ms TTL | `INSUFFICIENT` | `STALE` | EO-009 |
| 3 | `negative-wrong-target` | 观测目标 `service:core-db` 与契约不一致 | `INSUFFICIENT` | `WRONG_TARGET` | EO-005 |
| 4 | `negative-observed-revision-r16` | 本轮绑 r17，响应明确 r16 | `CONTRADICTED` | `WRONG_REVISION` | EO-007 / EV-002 |
| 5 | `negative-old-binding-revision` | 采集任务绑定 r16（旧任务） | `INSUFFICIENT` | `WRONG_REVISION` | EO-006 |
| 6 | `negative-missing-field` | 缺 `observed_revision` 键（不是 null） | `INSUFFICIENT` | `MALFORMED` | EO-002 / EO-008 |
| 7 | `negative-malformed-payload` | payload 不可解析 | `INSUFFICIENT` | `MALFORMED` | EO-008 |
| 8 | `negative-timeout` | 全部连接超时 | `INSUFFICIENT` | `TIMEOUT` | EO-008 / 3.3 |
| 9 | `negative-source-conflict` | 未登记采集器报 false，受信来源报 true | `INSUFFICIENT` | `CONFLICT` | EV-003 |
| 10 | `negative-different-round` | 用 round 1 证据核验 round 2 | `INSUFFICIENT` | `MISSING` | EO-010 |
| 11 | `negative-duplicate-observation-id` | 重复 ID 不填槽 | `INSUFFICIENT` | `MISSING` | EO-011 |
| 12 | `negative-empty-obligations` | `obligations=[]`，契约被拒绝 | `INSUFFICIENT` | `MISSING` | EO-001 |
| 13 | `negative-window-missing-sample` | 仅 2 组有效采样 | `INSUFFICIENT` | `MISSING` | W-003 / EO-012 |
| 14 | `negative-future-timestamp` | `observed_at > decision_time` | `INSUFFICIENT` | `MALFORMED` | EO-009 |
| 15 | `negative-passed-but-business-false` | `StateVerifier.passed=true` 但业务字段 false | `CONTRADICTED` | `[]` | EV-002 / 第 8 节 |
| 16 | `negative-cross-scope` | 观测来自另一租户/工作空间 | `INSUFFICIENT` | `MISSING` | EO-004 / 3.1 |
| 17 | `negative-missing-collector-identity` | 缺 `collector_id` | `INSUFFICIENT` | `MALFORMED` | EO-003 / EO-002 |
| 18 | `negative-partial-instance-recovery` | 两实例只恢复一个 | `CONTRADICTED` | `[]` | EV-002 / 3.3 |
| 19 | `negative-single-sample-jitter` | 6 条中仅 1 条 false，不作多数投票 | `CONTRADICTED` | `[]` | 3.1 补充 / 3.3 |

1-15 为 `semantics.md` §10 冻结清单；16-19 为任务书追加反例（跨 scope、缺采集器身份、部分实例恢复、单样本抖动）。`test_counterexample_acceptance_list_is_covered` 断言这 19 个 ID 必须齐全，缺一即失败。

另有两组边界样例在 `test_evaluator.py`：`timeout_is_failure=true` 的可达性反例（CONTRADICTED）、空观测集（INSUFFICIENT/UNKNOWN）。

## 4. 命令级证据

| 命令 | 结果 | 说明 |
|---|---|---|
| `python -m pytest tests/recovery_contracts -q` | `125 passed, 1 skipped in 0.36s` | SKIP = `jsonschema` 未安装，记 `SKIP` 不伪装 `PASS` |
| `python -m pytest tests -q` | `441 passed, 24 skipped in 108.20s` | 24 skip 均为既有外部依赖（Spring Boot / MySQL / Redis / 未设 `SMARTOPS_AGENT_URL`）+ 上述 1 条 jsonschema |
| `python -m pytest ai-service/app/tests -q` | `53 passed in 4.34s` | 确认未影响 ai-service |
| `git status --porcelain` | 本次改动仅 `agent/recovery_contracts/`、`tests/recovery_contracts/`（及本报告） | 工作树其余 `M`/`??` 条目来自并行任务，非本次改动；未修改任何既有运行代码 |
| 环境 | Python 3.14.3 / pytest 9.1.1 / `jsonschema` 未安装 | 版本决定 SKIP 项，不是失败 |

## 5. 未做与仍需闭环（如实列出）

| 项 | 状态 | 归属 |
|---|---|---|
| `ProbeDecision`（`choose_next`） | `NOT_STARTED` | PROBE-P1-01 |
| `ReplayBundle` / `replay` | `NOT_STARTED` | REPLAY-P1-01 |
| 接入 pipeline / 计划-工具契约声明核验 | `NOT_STARTED` | PLAN-RUN-P1-01（无 ProbeDecision 来源前无法接线） |
| Schema 全量校验（`jsonschema`） | `SKIP` | 未安装依赖；已用代码层等价校验（必备字段、常量、枚举、id 模式）覆盖，但不等同完整 Schema |
| `expires_after` 强制生效 | 已建模校验、未强制计时 | 冻结 schema 无契约创建时间字段，无法定位计时起点；见 `semantics.md` §11.2 |
| 谓词注册表覆盖 | 3 个模板（`business_health_flag` / `all_instances_recovered` / `endpoint_reachable`） | 未登记谓词直接拒绝，避免 LLM 自由文本成为谓词 |
| 自然语言“已恢复”识别 | 不做 | 只接受 `claim_type=BUSINESS_RECOVERY`；自然语言仅可作候选 Claim |
| `artifact_digest` 对 error-only 观测 | 消费侧约定（对 error 对象做 canonical 摘要） | 冻结 schema 未细分，已写入实现注释；需 N01 后续版本化确认 |

## 6. 环境与规范偏差

1. **`docs/design/recovery-contract-v1/examples/` 存在并行写入**。该目录是 N01 规范目录，本次执行期间被另一写入者以不同元数据约定（`example_id` / `kind` / `expected_rule` / `input_schema_valid` / `invalid_object`）重写；其中 6 条契约的 `digest` 未随内容重算，1 条为故意非法的空义务契约。按冻结规则“digest 必须与 canonical 摘要一致”，这些文件被本实现拒绝（属正确行为，不是缺陷）。
   - 处置：不改写 N01 目录文件（协作规则：N01 唯一写入者）；可执行样例包放 `tests/recovery_contracts/fixtures/`，文件名加 `vp01-` 前缀避免与并行写入冲突。
   - 交叉核对：用同一实现跑 `examples/` 的 19 条输入，期望 verdict 与 `expected_verdict` **19/19 一致**（其中 7 条在契约解析层即被拒绝：6 条 digest 不一致 + 1 条空义务）。结论是语义一致、仅元数据与完整性状态不同。
2. **样例清单判断在 `tests` 侧校验**。`test_examples.py` 注明的 `SCHEMA_PATH` 指向冻结 `schema.json`，仅在 `jsonschema` 可用时校验；缺依赖时显式 SKIP。
3. **`.runtime/ver-p0-01/` 下的一次性脚本**（样例生成、交叉核对）不属交付物，未纳入版本库。

## 7. 回滚方式

- 完整移除：删除 `agent/recovery_contracts/` 与 `tests/recovery_contracts/`，其余代码零改动，无需数据迁移。
- 停用新签发（保留审计）：不再调用 `verify()` / `ReceiptLedger.issue()`；已落盘的 JSONL 审计文件可用 `ReceiptLedger(path=...)` 只读回读，历史回执与失效事件保持可查（`test_history_survives_issuance_being_disabled` 覆盖此路径）。
- 历史回执不可改写：失效只追加 `EXPIRED` / `NEW_COUNTEREXAMPLE` / `REVISION_CHANGED` / `EVIDENCE_RETRACTED` 事件；当前视图优先级 `INVALIDATED > EXPIRED > ACTIVE`。

## 8. 结论

按任务书 L98-L110 的可实现范围完成：结构化业务条件驱动的三值判定、3 组 A/B 采样窗、有限期回执与只追加失效事件、审计可回读。19 条验收反例（含 4 条任务书追加项）与 1 条真恢复正例全部按期望判定，未修改既有运行代码。`ProbeDecision`、`ReplayBundle` 与 pipeline 接线按任务书依赖关系留待 PROBE-P1-01 / REPLAY-P1-01 / PLAN-RUN-P1-01，未伪称完成。
