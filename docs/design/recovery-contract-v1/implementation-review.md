# 候选实现审阅：recovery_contracts（C1）

- 日期：2026-11-05
- 审阅对象：`agent/recovery_contracts/{__init__,models,evaluator,receipts}.py`、`tests/recovery_contracts/test_*.py`
- 审阅方式：静态阅读 + 定向测试（本次获用户授权 RUN）
- 审阅人：协调者（**非独立审阅**；独立审阅仍为 `NOT_RUN`）
- 冻结依据：`docs/design/recovery-contract-v1/schema.json`、`semantics.md`
- 结论：**可作为 N02/N04 候选基线，不可标记 VERIFIED**；存在 1 个 P1 确定性缺陷与 2 个验证缺口，需在 HC-11 前处理。

## 1. 运行证据

命令（工作目录 `d:\SmartOpsAgent`）：

```text
python -m pytest tests/recovery_contracts -q -p no:cacheprovider --tb=short
```

结果：`125 passed, 1 skipped in 0.22s`，退出码 0。

跳过项：`tests/recovery_contracts/test_examples.py:141` —— 未安装 `jsonschema`，完整 JSON Schema 校验记 `SKIP`，实现方没有伪装成 PASS（符合门禁规则）。

当前环境：Python 3.14.3；`import jsonschema` → `ModuleNotFoundError`。

## 2. 覆盖映射（schema ↔ 实现）

| schema 对象 | 实现 | 状态 |
|---|---|---|
| Target / Window / Budgets / Obligation | `models.py` 同名 dataclass | 已实现 |
| RecoveryContract | `models.py:344-427` | 已实现；空义务集抛 `ContractError`（`evaluator.py:498-500` 再校验） |
| Claim | `models.py:429-474` | 已实现；校验 `contract_digest` 绑定 |
| EvidenceObservation | `models.py:484-577` | 已实现；严格字段集 + payload digest |
| ObligationResult | `models.py:588-646` | 已实现 |
| VerificationReceipt | `models.py:647-...`、`receipts.py:73-151` | 已实现；非 VERIFIED 强制 `NOT_ISSUED` + 时间为 null |
| ProbeDecision | **无** | N03 未开始 |
| ReplayBundle | **无** | N05 未开始 |

实现没有伪称已完成 N03/N05；`__init__.py` 的导出也仅覆盖已实现对象。

## 3. 通过的关键语义

1. 反例优先：任一合格 COUNTER 直接判该义务 `FALSE`，不做多数投票（`evaluator.py:401-422`）。
2. 空样本不放行：`all_instances_recovered` 遇空列表返回 UNDETERMINED/MALFORMED（`evaluator.py:109-111`）。
3. 超时默认不是业务失败，只有契约显式 `timeout_is_failure` 才判 FALSE（`evaluator.py:239-248`）。
4. 窗口规则已落地：三组、组内偏差、首末跨度、相邻间隔、下一组最早启动（`evaluator.py:282-337`）。
5. 回执有效期取 `min(签发+receipt_ttl, 每条使用证据+evidence_ttl)`（`receipts.py:97-107`）。
6. 重复证据 ID 不算新增样本、但保留审计拒绝（`evaluator.py:530-533`）。
7. 证据快照与逐义务拒绝码可追溯，`rejected_evidence` 写入回执 extensions（`receipts.py:146-150`）。

## 4. 审阅发现

| ID | 级别 | 发现 | 证据 | 建议 |
|---|---|---|---|---|
| R-01 | **P1** | `evidence_snapshot_digest` 依赖调用方传入顺序：`used_observations` 直接按 `parsed` 顺序取用，同一证据集合换序会生成不同回执摘要，破坏"同证据同指纹"与回放可比性 | `evaluator.py:596`；对比 `receipts.py:130-132` | 摘要前按 `(observed_at, sequence, id)` 规范排序；补一个输入逆序仍得到同一 digest 的测试 |
| R-02 | **P1** | Schema 一致性未被自动验证：缺 `jsonschema`，20 个示例只做了 JSON 语法与手工断言 | 测试 SKIP（`test_examples.py:141`） | 在开发依赖中显式加入 `jsonschema`（需依赖变更授权），把 SKIP 转成 PASS 或继续保留 `NOT_RUN` 声明 |
| R-03 | P1 | `endpoint_reachable` 在 `error is None` 时直接 SUPPORT，不检查状态码/业务体；若未来探针把 HTTP 500 记作 payload 而非 error，会误判"可达=恢复" | `evaluator.py:123-132`；`semantics.md:259` | 冻结探针契约：非 2xx/3xx 必须写 `error`，或谓词新增 `expected_status` 校验 |
| R-04 | P2 | `_strict_bool` 接受 `"true"/"yes"/"1"` 字符串，属于宽松强转；与"严格布尔"叙述不完全一致 | `evaluator.py:69-78` | 决定是否允许强转并写入 semantics；若不允许，仅接受 JSON `true/false` |
| R-05 | P2 | `expires_after` 已入 schema 但未参与求值/签发；合同登记时间 V1 为 UNKNOWN，过期契约仍可能签发 | `models.py:390`；`semantics.md:244` | 在 N04/N06 补齐可信登记时间前，明确"expires_after 不生效"并写入已知限制 |
| R-06 | P2 | `collector_version` 只记录、不校验版本漂移；同一 collector 升级后可继续用旧证据 | `receipts.py:115-117` | 决定是否在契约中冻结 collector 版本映射；若无，写入"版本漂移不阻断"的显式说明 |
| R-07 | P2 | 目标匹配只比对 `target_id`，未比对 `target_kind`；同名不同类目标可能串用 | `evaluator.py:219` | 同时校验 `target_kind`（必要时含 endpoint） |

未发现：默认 TRUE、空义务集签发、200/exit 0 直接当恢复、失败后多数投票洗白。

## 5. 处置建议（不改代码，交 C 批认领）

1. 先修 R-01 并加逆序输入测试——这是回放与回执可比性的地基。
2. 在同一改动批次内补 R-03 的探针契约说明，避免 N03 实现时踩坑。
3. R-02 需用户确认是否引入 `jsonschema` 开发依赖；未确认前，schema 一致性保持 `NOT_RUN`。
4. R-04/R-06/R-07 属规范取舍，先写进 semantics 的"已知限制/决策"再实现。
5. N03（probes/scheduler）与 N05（replay）尚未开始，不在"候选实现"范围内。

## 6. 状态

```yaml
task: C1 candidate-implementation-review
mode: REVIEW
targeted_tests: PASS (125 passed / 1 skipped / exit 0)
schema_conformance: NOT_RUN (jsonschema missing)
determinism: AT_RISK (R-01)
implementation_modified: false
independent_review: NOT_RUN
verdict: ADOPT_AS_CANDIDATE_WITH_FIXES
```

## 7. C2 处置结果（2026-11-05 追加）

| 发现 | 处置 | 证据 |
|---|---|---|
| R-01 | **已修**：`used_observations` 改为 `_ordered(...)`，摘要前按 `(observed_at, sequence, id)` 规范排序 | `agent/recovery_contracts/evaluator.py:596` |
| R-01 回归 | **已加测试**：同一证据集合正序/逆序签发得到相同 `evidence_snapshot_digest` | `tests/recovery_contracts/test_receipts.py:211-237` |
| R-03 | **已冻结规则**：非 2xx/3xx 必须写 `error`；`endpoint_reachable` 不得代替业务谓词 | `docs/design/recovery-contract-v1/semantics.md:268-273` |
| R-02 | 仍 `NOT_RUN`：`jsonschema` 未安装；是否引入开发依赖待决策 | — |
| R-04/R-05/R-06/R-07 | 保持规范取舍项，未改实现 | — |

C2 后定向测试：`126 passed, 1 skipped, exit 0`（新增 1 个顺序不变性用例）。

```yaml
task: C2 fix-determinism
mode: IMPLEMENT + RUN
changed_files: [agent/recovery_contracts/evaluator.py, tests/recovery_contracts/test_receipts.py, docs/design/recovery-contract-v1/semantics.md]
targeted_tests: PASS (126 passed / 1 skipped / exit 0)
schema_conformance: NOT_RUN
production_verdict_claimed: false
```

## 8. N03 抽查（2026-11-05 追加）

新增 `probes.py`（377 行）、`scheduler.py`（454 行）与两个测试文件；协调者只做抽查，非逐行审阅。

| 检查点 | 结果 |
|---|---|
| 确定性 | `choose_next` 纯函数、无随机/无系统时钟；排序 `(-score, cost, probe_id)`，固定顺序基线只按 `probe_id` |
| 评分 | `score = 尚缺必需义务权重和 / max(cost,1)`，与 semantics §5 一致 |
| 预算 | run 级 `calls_used`/`deadline` 不随轮次重置；STOP 原因枚举完整；采样槽未到返回 WAIT 且不扣调用 |
| 探针执行器 | 仅注入 `transport/clock`，固定 `127.0.0.1`、GET、禁代理/重定向、4KiB、1s 绝对超时；非 2xx/3xx 只写 `error`，不塞 payload |
| 真实接入 | **未做**：没有内置 socket transport，也未启动任何服务；HC-11 前必须补真实 loopback transport 与运行证据 |
| 回归 | `179 passed, 1 skipped, exit 0`（skip 仍为 jsonschema） |

结论：N03 属"候选完成"，可进入 N05/HC-11，但不能对外声称已跑过真实链路。

## 9. N05 与 HC-11 运行结果（2026-11-05 追加）

### 9.1 N05 同证据回放

- 新增 `agent/recovery_contracts/replay.py`（1195 行）与 `tests/recovery_contracts/test_replay.py`（18 个用例，全部通过）。
- `replay_state`：`COMPLETE / REPLAY_INCOMPLETE / MALFORMED / STALE`。
- 缺录制探针 → `REPLAY_INCOMPLETE` 并列出 `probe_id`/`obligation_ids`，`verdict=null`，不补探、不默认 TRUE。
- 变体回放（r17→r16、时间偏移、删除证据）复现 `VERIFIED→INSUFFICIENT`，差异码 `EXPECTED_REVISION_CHANGED`/`EVIDENCE_TIME_SHIFTED`/`EVIDENCE_REMOVED`/`VERDICT_FLIPPED`。
- 同一证据包 100 次重放：输出、逐义务结果、摘要唯一一致；不读墙钟、不联网、不调 LLM。

### 9.2 HC-11 loopback 演示（真实 HTTP，仅 127.0.0.1）

命令：`python scripts/research/recovery_contract_demo.py` → 退出码 0。
证据：[`.runtime/hc-11/summary.md`](../../.runtime/hc-11/summary.md)、[`run.json`](../../.runtime/hc-11/run.json)。

| 场景 | 实际结果 | 说明 |
|---|---|---|
| A 全健康 | `VERIFIED` / 回执 `ACTIVE` | 3 来源组 × 3 采样组 = 9 条观测，首末约 4.9s，窗口满足 |
| B HTTP 200 但 `healthy=false` | `CONTRADICTED` / `NOT_ISSUED` | 反例即停，未因 200 判恢复 |
| C 来源 502 | `INSUFFICIENT` / `NOT_ISSUED` | 观测 `error=HTTP_502`，义务 UNKNOWN，不是 FALSE/TRUE |
| D 回放 r17→r16 | `INSUFFICIENT`，差异码 2 个 | 原录制 VERIFIED，回放不补探（stub 请求增量 0） |

隔离：仅绑定 `127.0.0.1:58343`，无外网、无 LLM、无随机；4KiB、1s、禁代理/重定向；动作轴 `NOT_PERFORMED`（未执行任何真实修复或审批）。

### 9.3 当前测试总量

- 全包：`205 passed, 1 skipped, exit 0`（skip 仍为 `jsonschema` 未安装）。
- 并行 AI 新增的 3 个真实 socket 测试最初因 WinError 10038 失败，随后由其自行修复；本会话未改动其文件。

### 9.4 仍不能宣称的结论

1. 这不是平台闭环：Java/审批/租户/Run 权威未接入（N06 未做）。
2. 这不是"真实修复成功"：动作轴未执行。
3. oracle 已补（N08），但它由同一协调者按同一份 schema/semantics 编写，不是外部独立团队审阅；fixture 与 real 尚未独立分账。
4. Schema 一致性仍 `NOT_RUN`；`receipt_ttl` 生产取值与合同到期可信来源仍 UNKNOWN。

## 10. N08 独立 oracle 与 N07 三张卡（2026-11-05 追加）

### 10.1 N08：独立 oracle × 强基线

- 新增 `scripts/research/recovery_contracts/independent_oracle.py`（953 行，仅标准库 + schema/semantics 常量，不 import 被测实现）与 `run_experiments.py`（885 行，42 案例 / 5 个判定器）。
- 报告：[`docs/evaluation/recovery-contracts/n08-report.md`](../../evaluation/recovery-contracts/n08-report.md)；产物 `.runtime/n08/{report.json,summary.md}`。
- 修复后指标：实现假 VERIFIED **0/42（0/35）**；与 oracle verdict 一致 **41/42**；原因码集合一致 **41/42**。三条弱基线假 VERIFIED 分别为 21/42、17/42、33/42。
- 探针调用恒为 0（冻结证据回放，不调度真实探针）。

### 10.2 R-08（P0 假 VERIFIED，已修）

| 项 | 内容 |
|---|---|
| 发现 | `divergence-multi-target-window`：义务 A 采 `sg-a`（target `service:edge-nginx`），义务 B 采 `sg-b`（target `service:b`）；实现按 source_group 直接配对，未校验同组 target，输出 `VERIFIED` |
| 修复 | `evaluator.py::evaluate_window` 增加同组 target 一致性检查；不一致的候选组不进入有效窗口 |
| 附带修复 | `Evaluation.reason_codes()` 在 `INSUFFICIENT` 且窗口未满足时并入 `window.reasons`，使窗口缺口在结论层可见 |
| 回归 | `test_independent_oracle.py::test_multi_target_window_is_rejected`：断言 `INSUFFICIENT`、窗口不满足、原因码含 `MISSING` |
| 复测 | 实现假 VERIFIED 由 1/42 降为 0/42；原因码集合一致由 37/42 升至 41/42；全包 `219 passed, 1 skipped, exit 0` |

仍未对齐的 1/42 分歧为 `negative-source-conflict`（实现 `CONTRADICTED`、oracle `INSUFFICIENT`），根因是 V1 schema 没有“来源身份是否已确认”字段。

### 10.3 N07：前端三张恢复卡

- 新增 `frontend/src/components/operations/recovery/{GapCard,ContractCard,ReplayCard}.vue` 与纯展示映射 `recoveryCards.js`、fixture `fixtures.js`。
- 覆盖：义务三值/原因码/被拒证据/下一探针建议/预算、四轴与 `receipt_state`/`valid_until`/窗口、`replay_state` 与逐义务差异/缺失探针。
- `passed` 只在纠察轴展示，不能替代恢复轴；空义务、`NOT_ISSUED`、`REPLAY_INCOMPLETE` 都有显式提示。
- 测试：`frontend/test/recovery/recoveryCards.test.mjs` 9 项全绿；`vue-tsc` 通过。
- 未做：未接入真实 API，未做浏览器端到端；卡片数据仍来自 fixture。

```yaml
task: N08-oracle-and-N07-cards
mode: IMPLEMENT + RUN
changed_files:
  - agent/recovery_contracts/evaluator.py
  - tests/recovery_contracts/test_independent_oracle.py
  - scripts/research/recovery_contracts/{independent_oracle.py,run_experiments.py}
  - frontend/src/components/operations/recovery/*
  - frontend/test/recovery/recoveryCards.test.mjs
targeted_tests: PASS (219 passed / 1 skipped / exit 0)
schema_conformance: NOT_RUN
false_verified: 0 / 42
production_verdict_claimed: false
```

## 11. 独立上下文审阅与 R-09/R-10（2026-11-05 追加）

### 11.1 审阅方式与边界

- 由一个**未参与实现、未携带本会话上下文**的子代理独立审阅 `agent/recovery_contracts/` 与 `semantics.md`，只读、不改代码、不启动服务。
- 该审阅仍由同一模型体系执行，**不等同于外部第三方审阅**；结论只用于发现偏差，不用于宣称独立验证通过。

### 11.2 发现的可证实偏差

| # | 级别 | 位置 | 问题 |
|---|---|---|---|
| 1 | P0 | `evaluator.py` 义务求值 | 填满 TRUE 槽后提前返回；未登记采集器/scope 不符的 COUNTER 只置 `ineligible_counter` 后被忽略 → 假 VERIFIED |
| 2 | P1 | `evaluator.py` 资格过滤 | `run_id`/`verification_round` 为 `None` 时跳过过滤，冻结签名直接调用可让异轮证据进入 |
| 3 | P1 | `evaluator.py` scope 缺省 | `authorized_scopes` 缺省为 `{contract.scope}`，等于信任观测自述 scope |
| 4 | P1 | `evaluator.py` 重复 ID | 先到先得；同 ID 一 TRUE 一 FALSE 时 verdict 与摘要随输入顺序变化 |
| 5 | P1 | `replay.py` | 不核对录制回执的 `evidence_snapshot_digest`/`contract_digest`；替换观测并重签包摘要仍可返回 COMPLETE |
| 6 | P2 | `receipts.py` | `current_receipt` 缺省不判 EXPIRED；历史回执入账后恒 ACTIVE |
| 7 | P2 | `probes.py` | `elapsed_ms` 静默截到 1000，实际超时调用可虚过组间间隔 |
| 8 | P2 | `evaluator.py` | `endpoint_reachable` 只看 `error is null`，未校验 payload 内 5xx |
| 9 | P2 | `models.py` | `from_dict` 未执行 schema 的 `allOf`；`VERIFIED` + `issued_at=null` 可通过 |

### 11.3 已处置

| 缺陷 | 处置 | 回归 |
|---|---|---|
| R-09（上表 #1，P0 假恢复） | 在 TRUE 返回前计算 `conflict`，`conflict=True` 时不返回 TRUE，落到 UNKNOWN 并带 `CONFLICT` | `test_unqualified_counterexample_blocks_true_slots` |
| R-10（上表 #4，顺序依赖） | 解析前统计 ID 次数，出现重复 ID 时**所有副本**都记 `MISSING`、不填槽 | `test_duplicate_id_with_conflicting_payload_is_order_invariant` |
| R-11（上表 #5，P1 回放可被重签） | 原历史包重算证据快照摘要并与录制回执 `evidence_snapshot_digest` 对照；不一致返回 `STALE` + `EVIDENCE_SNAPSHOT_MISMATCH`（变形包仍按 `mutation_diff` 登记差异） | `test_resigned_evidence_with_same_claim_is_stale` |
| R-12（上表 #2，P1 绑定可跳过） | 调用方未声明 `run_id`/`verification_round` 时，自述该字段的观测视为归属不可确认：`run_id` → `STALE`，`verification_round` → `MISSING`。规则已写入 semantics §3.1 | 全包回归 + N08 重跑 |
| R-13（上表 #3，P1 授权可缺省） | `verify()` 的 `authorized_scopes` 改为必填，删除“缺省即 `{contract.scope}`”；调用方（测试/HC-11/replay 复算）显式传入 | 全包回归 |

复测：`tests/recovery_contracts` **223 passed / 0 skipped**；N08 实现与 oracle verdict **42/42** 一致、假 VERIFIED 0/42（原因码一致 39/42，差异为“归属不可确认”的表达粒度）；HC-11 重跑退出码 0，四场景结论不变。

### 11.4 未处置（仍为已知缺口）

| 项 | 原因 | 建议 |
|---|---|---|
| #6–#9 | 影响可观测性或畸形输入，不改变主路径 | 按 P2 排期 |

**规范未定义点**：§4.2 无 `group_id`；窗口按“各来源组第 i 条”对齐，与义务采样槽不是同一集合；replay 未使用 `source_mapping`/`observation_order`。这些需要先补规范，再改实现。

```yaml
task: independent-review-r09-r10
mode: REVIEW + MIN-FIX
changed_files:
  - agent/recovery_contracts/evaluator.py
  - tests/recovery_contracts/test_evaluator.py
targeted_tests: PASS (223 passed / 0 skipped / exit 0)
false_verified: 0 / 42
unfixed_p1: []
external_third_party_review: NOT_RUN
```



