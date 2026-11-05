# 恢复契约 v1 语义规范（N01 冻结稿）

- 设计版本：`recovery-contract/v1`
- 设计状态：`DONE`（仅本文件与同目录 schema/样例；业务代码 `NOT_STARTED`，实现与实测 `NOT_RUN`）
- 规范来源：`docs/development/SmartOpsAgent-全面整改与创新升级交接书-单文件版-20261105.md` 第 2 章、N01 卡（第 839-881 行）
- Schema：同目录 `schema.json`（JSON Schema draft 2020-12）
- 适用消费者：N02 求值器、N03 探针/调度、N04 核验/回执、N05 回放、N06 平台集成
- 变更规则：任何字段/枚举/阈值变更都必须新版本号并提交修订请求；N02-N05 不得各自改名、放宽或静默兼容旧字段。

本文件只冻结**类型、状态、字段、时间/预算/轮次语义**。交接书中 `passed/exit 0/HTTP 200/审批 approved` 一律不是恢复证据；它们分别属于 inspection、action、transport、authorization 轴。

---

## 1. 六类状态词典（不可互相替代）

| 概念 | 可取值 / 含义 | 本规范承载位置 | 禁止混用 |
|---|---|---|---|
| action | 动作计划/审批/执行/终态；隔离只读 PoC 为 `NOT_PERFORMED`；动作状态列表由 HC-01 冻结，另含正常、拒绝、取消、过期和重启中断的合法转移；`degraded` 单列为降级属性 | 不在本 schema；由 HC-01 的 Action/Run 模型承载 | 诊断 GET 返回 200 不是“修复动作成功”；审批通过不是恢复 |
| inspection | Inspector 结果及原始 `StateVerifier.passed` | 现有 `InspectionResult.verification_result`；由 N01 保留原义，不重命名 | `passed` 表示声明与观测一致，不表示业务已恢复；声明未恢复且探针异常也可能 `passed` |
| recovery | `VERIFIED` / `CONTRADICTED` / `INSUFFICIENT` | `VerificationReceipt.verdict`、`ObligationResult[]` | action 成功不代表业务恢复；`VERIFIED` 不是执行许可 |
| authorization | 身份、scope、审批、过期、消费状态 | 平台现有审批/grant；本 schema 不定义、不签发 | 恢复回执不授予执行权限，不自动触发重启、变更或提权 |
| 证据平面 | 每条义务 `TRUE` / `FALSE` / `UNKNOWN` 及原因码，见 `ObligationResult` | `ObligationResult.value` + `reason_codes` | 证据平面独立，不能替换 inspection 轴；`UNKNOWN` 不能被更多无关证据补齐，也不能当 `FALSE` 抵消 |
| receipt_state | `NOT_ISSUED` / `ACTIVE` / `INVALIDATED` / `EXPIRED` | `VerificationReceipt.receipt_state` | `ACTIVE` 需历史 `VERIFIED` 且当前仍有效；“曾经运行过核验”不等于有效回执 |

此外：

- `UNKNOWN` 是**义务值**；`INSUFFICIENT` 是**恢复判定**；`INTERRUPTED` 是**轮次/运行中断原因**。三者不得拼成一个状态字段。
- `CONFLICT` 原因码本身不决定三值：来源或身份未确认的冲突只构成 `UNKNOWN`；已确认同目标、同轮次且明确违反业务谓词的观测构成 `FALSE`。
- 不得用多数投票消除业务失败证据。

---

## 2. 七个对象与字段冻结

字段全集以 `schema.json` 为准。下表只列冻结要点，便于审阅：

| 对象 | 必须字段（N01 卡） | 关键约束 |
|---|---|---|
| `RecoveryContract` | `schema_version`、`id`/`version`、`scope`、`target`、`expected_revision`、`template_id/version`、`obligations`、`source_groups`、`window`、`budgets`、`expires_after`、`digest` | `obligations` `minItems=1`（空义务集拒绝）；`source_groups` `minItems=2`；窗口/预算阈值用 `const` 冻结；仅支持已审核模板 |
| `Claim` | `id`、`contract_digest`、`scope`、`target`、`expected_revision`、`claim_type` | V1 只批准 `BUSINESS_RECOVERY`；自然语言只生成候选 Claim，可信判定使用结构化模板 |
| `EvidenceObservation` | `id`、`run_id`、`verification_round`、`collector_id/version`、`probe_id`、`scope/target`、`binding_revision`、`observed_revision`、`source_group`、`sequence`、`observed_at`、`elapsed_ms`、`payload/error`、`artifact_digest` | `payload` 与 `error` 至少一个非 null；`observed_revision` 允许 null（未报告）；`elapsed_ms` 上限 1000 |
| `ObligationResult` | `obligation_id`、`value`、`reason_codes`、`used_evidence_ids`、`rejected_evidence` 及原因、`checked_at` | `TRUE` 时 `reason_codes` 必须为空；`UNKNOWN` 时必须至少一个原因码 |
| `ProbeDecision` | `decision_id`、`policy_version`、候选与过滤理由、`score`、`selected_probe_id` 或 `WAIT`/`STOP`、预算前后值 | `SELECTED` 必须有 `selected_probe_id`；`WAIT` 必须有 `next_eligible_at`；`STOP` 必须有 `stop_reason` |
| `VerificationReceipt` | `id`、三类输入摘要、版本、`run_id`/`verification_round`、目标绑定、逐义务结果、`verdict`、`receipt_state`、`issued_at`、`valid_until`、失效事件引用 | 非 `VERIFIED` 时 `receipt_state=NOT_ISSUED` 且 `issued_at=valid_until=null`（schema 条件强制） |
| `ReplayBundle` | `schema_version`、冻结输入与策略配置、显式逻辑时钟/顺序、预录探针映射、预算、依赖版本、整体摘要 | 冻结 `contract`/`claim`/`observations`/`policy_config`/`decision_clock`/`observation_order`；变形包必须新 `bundle_id`、`digest`、`parent_bundle_id`、`mutation_diff` 且 `is_historical_fact=false` |

`extensions` 只用于未冻结扩展数据；放入其中的字段在 V1 一律按 `UNKNOWN` 处理，不得参与必需判定。已冻结字段禁止改名后塞进 `extensions`。

### 2.1 摘要与 canonical JSON

- 编码：UTF-8。
- 对象键按 Unicode 码位升序排列。
- 不输出任何无意义空白；数组顺序保持；`null` 保留。
- 数值使用最短可往返表示，禁止 `NaN` / `Infinity`。
- `digest` 计算：删除对象自身 `digest` 字段后的 canonical JSON 做 SHA-256，输出 `sha256:` + 64 位小写十六进制。
- `VerificationReceipt` 的 `evidence_snapshot_digest` 是对参与判定的观测快照（按显式顺序、保留原字节摘要）做同样规则计算。
- hash 只保证字节一致，不证明采集事实真实；真实性仍依赖采集器身份、权限与存储控制。
- 回放完整性必须对照**外部受信 expected digest**；原包被篡改直接拒绝，不得一边声称拒绝篡改、一边修改冻结历史继续求值。

---

## 3. 三值判定公式

### 3.1 观测资格 `Eligible(e)`

```text
Eligible(e) =
     collector_registered(e.collector_id)          // 受信采集器登记，且 source_group 已登记
  ∧ scope_authorized(e.scope)                     // 当前主体有权查看
  ∧ target_equal(e.target, contract/obligation.target)   // target_id 精确相等
  ∧ e.binding_revision == contract.expected_revision      // 采集任务绑定版本匹配
  ∧ schema_valid(e) ∧ artifact_digest_valid(e)
  ∧ e.verification_round == current_verification_round
  ∧ e.observed_at <= decision_time                // 未来时间不合格
  ∧ decision_time - e.observed_at <= 15000ms      // 证据时效
  ∧ e.id 不是已出现的重复观测 ID
```

补充规则：

- `collector_registered` 由服务端身份、来源组登记和人工审阅确认；不由 URL 不同、LLM 文本或操作者自述推断。
- `scope_authorized` 使用服务端主体身份与可见范围，不使用客户端提交的标签。
- `target_equal` 只比较 `target_id`；`endpoint`、显示名不参与相等性。
- 同一 `target_id` 的 `/health` 与 `/ready` 若只是同一内部缓存的两个别名，视为同一来源组。
- 重复 ID 不算新增采样；重复记录保留审计但不填补采样槽。
- 乱序以 `sequence` + `observed_at` 重建，不按数组下标；不得用滑动窗口抹掉失败。

### 3.2 观测到义务值的映射

```text
OBS(e) =
  SUPPORT      若 e 合格 且 predicate(e.payload) == true
  COUNTER      若 e 合格 且 predicate(e.payload) == false
  UNDETERMINED 其他（不合格 / 未报告 / 冲突未决 / 错误）

// binding_revision 已匹配但响应 observed_revision 明确不同：
// 这是“本轮版本义务的有效反例”，映射为 COUNTER，不得过滤成“无关旧记录”。
```

### 3.3 义务值

```text
OBL(o) =
  FALSE    若存在 e：合格 ∧ 指向 o ∧ OBS(e)=COUNTER
  TRUE     若不存在 COUNTER
           ∧ 窗口内该义务要求的每个采样槽都由合格且 SUPPORT 的观测填满
           ∧ 不存在来源/身份未决的冲突
  UNKNOWN  其他
```

- 无效或过期观测一律 `UNKNOWN`，不能当 `FALSE` 后随意抵消，也不能被更多无关证据补齐。
- 采集器连接超时默认 `UNKNOWN`；只有契约明确“从该观测位置可达”是业务条件时，才可把该条件判 `FALSE`（`FALSE` 的谓词必须是冻结的业务谓词，而不是传输错误）。
- 已确认同目标、同轮次且明确违反业务谓词的观测是 `FALSE`；来源或身份尚未确认的冲突只构成 `UNKNOWN`。

### 3.4 恢复判定

```text
verdict =
  CONTRADICTED  若存在任一必需义务 OBL=FALSE
  VERIFIED      若所有必需义务 OBL=TRUE ∧ 时间窗口满足
  INSUFFICIENT  其他（无 FALSE，但仍缺证据 / 冲突未决 / 中断）
```

可选义务（`required=false`）的 `FALSE` 只保留反例与缺口卡，不单独把结论改为 `CONTRADICTED`；但它仍参与回放 diff 与后续审阅。

### 3.5 原因码选择规则

| 原因码 | 何时写入 | 典型值 |
|---|---|---|
| `MISSING` | 当前轮次没有合格观测、采样槽未填满、证据属于其他轮次、契约没有可计算义务 | `UNKNOWN` |
| `STALE` | 合格观测存在但 `decision_time - observed_at > 15000ms`，或证据已作废/到期 | `UNKNOWN` |
| `WRONG_TARGET` | 观测 `target_id` 与义务/契约目标不一致 | `UNKNOWN` |
| `WRONG_REVISION` | `binding_revision` 不匹配（旧任务/别轮任务）→ `UNKNOWN`；`binding_revision` 匹配但 `observed_revision` 明确不匹配 → 有效反例 `FALSE` | `UNKNOWN` / `FALSE` |
| `CONFLICT` | 同目标同轮次观测互相矛盾且来源/身份未确认 | `UNKNOWN` |
| `TIMEOUT` | 采集器超时/连接超时，默认不当业务失败 | `UNKNOWN` |
| `MALFORMED` | schema 缺字段/类型错误、摘要不符、payload 不可解析、未来时间 | `UNKNOWN` |

`CONFLICT` 本身不决定三值；来源已确认且违反业务谓词时必须走 `FALSE`，不能以 `CONFLICT` 掩盖。

---

## 4. 时间规则（N02-N05 可直接实现）

### 4.1 时钟与原点

- 判定时钟 `decision_time` 来自 run 的**单调时钟**；`observed_at`、`issued_at`、`valid_until` 等展示与持久化字段使用 UTC ISO-8601。
- run 启动时登记 `monotonic_origin_id`；所有探针 deadline 从该原点计算。
- 单探针 deadline = `min(now_monotonic + 1000ms, run_deadline_at)`；**不是**“每次读都可再等 1 秒”。1 秒包含连接、完整 body 读取与解析。
- 进程重启后不得直接比较旧单调时钟。中断轮次记为 `INTERRUPTED` / `INSUFFICIENT`，不自动续采；新轮继承**持久化 run 预算**。若原 deadline 无法可信重建，终止该 run。

### 4.2 采样组与窗口

```text
group_time(g) = max(observed_at(A), observed_at(B))
                 // A/B 均须合格，且同轮、同 target、同 binding_revision

valid_group(g) =
     A、B 两个路径都有合格观测
  ∧ |observed_at(A) - observed_at(B)| <= 1250ms
  ∧ g 与前一有效组之间：
        first_eligible_start(g) >= group_time(prev) + 2000ms
        // 实际启动间隔仍需核对，不以计划时间替代事实

window_valid =
     valid_group 数量 >= 3
  ∧ group_time(last) - group_time(first) >= 4000ms
  ∧ 所有相邻有效组 group_time 间隔 <= 4000ms
```

- 组时间取两条有效观测采集时间的**较晚值**；组内最大偏差候选 1.25s（闭区间）。
- 首末相隔至少 4s；相邻组不超过 4s；下一组最早启动为前组完成后 2s。以上均为闭区间边界。
- 每组必须同时含 A/B 两个路径的观测；缺失任一路径则该组无效，不因另一路径正常而补齐。
- 重复 ID 不算新增采样；组内出现重复 ID 时该槽仍视为未填。
- 采样计划时间不是事实；实际时间越界不算满足。
- 证据年龄：签发时对**全部必需观测**检查 `decision_time - observed_at <= 15000ms`。
- 未来时间：`observed_at > decision_time` 直接不合格，原因码 `MALFORMED`，不得按“负年龄”放行。

### 4.3 预算

```text
max_probe_calls       = 12     // run 级；重试与窗口内后续采样都扣费
per_probe_timeout_ms  = 1000   // 单探针绝对时限
run_deadline_ms       = 30000  // run 级总 deadline；等待也受约束
evidence_ttl_ms       = 15000  // 签发时证据年龄上限
receipt_ttl_ms        >= 1000  // 契约冻结参数；生产取值尚未验证
```

- 等待、连接、完整读取与解析都受绝对 deadline。
- 每次调度前重核剩余调用、未完成采样的最低等待、保留超时开销与 deadline。
- 静态不相容（预算不足以完成最小窗口）必须在执行前拒绝契约；运行中不再可完成则 `STOP` 并给出缺口。
- 6 次调用在正常低延迟下即可完成最小窗口；网络接近超时上限时**不保证**仍通过，参数没有生产 SLO 含义。

---

## 5. 补证调度：WAIT / STOP

```text
score(p) = 本探针可检查的尚缺义务权重之和 / max(登记成本单位, 1)
```

1. 先按服务端身份、目标白名单、工具权限、只读限制、配额和 deadline 过滤候选。
2. 登记每个探针可覆盖的义务、确定的成本单位与观测来源组；登记本身不是观测结果。
3. 同分依次选择较低成本、固定 `probe_id`；每次只发一个探针，收到结果后重新计算。
4. 时序义务拆成尚未满足的采样槽；仅对当前可执行槽计算覆盖。
5. 后续采样槽未到时输出 `WAIT(next_eligible_at)`。等待不是无信息重试，不扣探针调用次数，但受总 deadline 约束。
6. 探针无新增有效信息达到预定次数就 `STOP`；但不能因采样槽尚未到时就触发该规则。
7. 存在有效业务反例时保持本轮 `CONTRADICTED` 并保存冲突；只有来源/身份未决的矛盾保持 `INSUFFICIENT`。

`ProbeDecision` 的候选过滤顺序固定为：`UNREGISTERED` → `IDENTITY` → `SCOPE` → `TARGET_ALLOWLIST` → `TOOL_PERMISSION` → `READ_ONLY` → `QUOTA` → `DEADLINE` → `COST` → `DUPLICATE`。`WAIT` 不是探针选择结果；`STOP` 不是恢复结论。

---

## 6. 轮次与重启

- 有效反例令本核验轮次终止。只有控制器确认环境阶段变化，或操作者明确重新验证，才能创建新的 `verification_round`。
- 新轮次复用冻结契约，但**不混用旧轮样本**；历史反例保留，不删除。
- 新轮次**不重置** run 级调用预算与 deadline；额度不足即停止。
- 不能靠滑动窗口默默抹掉失败。
- 同一目标的重试仍须重新检查版本和时效。
- 进程重启：中断轮次 `INTERRUPTED` / `INSUFFICIENT`，不自动续采；新 run 继承持久预算；原 deadline 不可可信重建则停止该 run。
- 回执时间可信度不明确时**不恢复 `ACTIVE`**，避免重启刷新额度或有效期。

`INTERRUPTED` 不是 `ObligationResult.value`，也不是 `verdict`。若实现需要持久化该原因，只能放在轮次/运行对象或 `extensions`（V1 标 UNKNOWN），不得把三个枚举拼成一个状态。

---

## 7. 回执语义

```text
只有 verdict == VERIFIED 才能签发 receipt_state == ACTIVE
CONTRADICTED / INSUFFICIENT  ->  receipt_state = NOT_ISSUED
                               issued_at = null
                               valid_until = null
```

```text
valid_until = min(
    issued_at + receipt_ttl_ms,
    min(每个被用于 TRUE 的必需观测的 observed_at + evidence_ttl_ms)
)
```

- `valid_until` 不晚于上述最小值；不得由 LLM 或操作者在失败后放宽。
- `expires_after` 是契约有效期（毫秒）。若无法获得可信登记时间，则不能臆造“合同绝对到期时间”；该外部登记时间在 V1 为 UNKNOWN，由 N04/N06 补齐来源。
- 回执引用 `contract_digest`、`claim_digest`、`evidence_snapshot_digest`、策略版本、采集器版本、目标 revision、`run_id`、逐义务结果、采样时间和有效期。
- 回执记录“截至该采样窗口、这些业务条件已被支持”。离散采样通过不表示两次采样之间持续健康；没有持续监测时不保证即时发现新故障。
- 已收到的新反例、已知目标 revision 改变、证据撤回或到期，令**当前有效视图**变为 `INVALIDATED` / `EXPIRED`；历史回执不可改写，只追加失效事件。
- 当前状态求值优先级：`INVALIDATED` > `EXPIRED` > `ACTIVE`；`NOT_ISSUED` 表示从未签发，不参与“曾经有效”的历史。
- 审批 grant 沿用平台现有来源；回执没有执行授权能力。

---

## 8. 明确否定：以下都不等于恢复

| 信号 | 实际含义 | 不能推出 |
|---|---|---|
| `StateVerifier.passed == true` | 声明与观测一致 | 业务恢复、窗口满足、回执可签发 |
| 命令 `exit 0` | 进程/命令正常结束 | 目标服务可用、业务谓词为真 |
| HTTP 200 / 3xx | 传输层或端点有响应 | 业务自检通过、下游 B 可用 |
| 审批 `approved` | 授权层允许某动作 | 动作已执行、执行后恢复 |
| Inspector `PASS` / `WARN` | 纠察轴结论 | 恢复 verdict |
| SSE `done` / run `succeeded` | 请求链路结束 | 业务恢复 |
| LLM/检索/操作者说“已恢复” | 声明或背景 | 实时健康事实 |
| 多数组采样通过（少于 3 组） | 采样不足 | 窗口满足 |
| 旧任务或别轮次的健康记录 | 历史信息 | 本轮合格证据 |
| `CONFLICT` 原因码 | 矛盾尚未定性 | 自动 `FALSE` 或多数投票结论 |

---

## 9. 逻辑接口（冻结为类型约定，不是已存在 API）

```text
evaluate(contract, claim, observations, decision_time) -> ObligationResult[]
choose_next(contract, results, registry, budget, decision_time) -> ProbeDecision
verify(contract, claim, observations, decision_time) -> VerificationReceipt
current_receipt(result_record, invalidation_events, decision_time) -> NOT_ISSUED|ACTIVE|INVALIDATED|EXPIRED
replay(bundle, policy_version) -> COMPLETE|REPLAY_INCOMPLETE + structured_decision
```

- `evaluate` 是纯函数：不联网、不读墙钟、不写存储。
- `verify` 只消费合格观测并生成回执记录；不执行动作、不创建审批。
- `replay` 不访问网络、不重新调用 LLM、不使用当前墙钟覆盖 `decision_clock`；选择未录制探针时返回 `REPLAY_INCOMPLETE`，不补造结果。

---

## 10. 示例与拒绝规则映射

样例位于 `examples/`。每个文件是测试包：`input` 内的每个对象按 `schema.json` 对应 `$defs` 单独校验；`expected_verdict` 与 `expected_reason_codes` 是期望结果。

| 文件 | 缺陷 | 期望 verdict | 期望原因码 | 规则 |
|---|---|---|---|---|
| `positive.json` | 无（3 组、A/B、r17、窗口满足） | `VERIFIED` | `[]` | EO-ALL / W-001..W-006 / RS-001 |
| `negative-stale-evidence.json` | 证据年龄 30s | `INSUFFICIENT` | `STALE` | EO-009 |
| `negative-wrong-target.json` | 观测目标 service:c | `INSUFFICIENT` | `WRONG_TARGET` | EO-005 |
| `negative-observed-revision-r16.json` | 本轮采集 r17，响应 r16 | `CONTRADICTED` | `WRONG_REVISION` | EO-007 / EV-002 |
| `negative-old-binding-revision.json` | binding r16（旧任务） | `INSUFFICIENT` | `WRONG_REVISION` | EO-006 |
| `negative-missing-field.json` | 观测缺 `observed_revision` 字段 | `INSUFFICIENT` | `MALFORMED` | EO-002 / EO-008 |
| `negative-malformed-payload.json` | payload 不可解析 | `INSUFFICIENT` | `MALFORMED` | EO-008 |
| `negative-timeout.json` | 采集超时 | `INSUFFICIENT` | `TIMEOUT` | EO-008 / 3.3 |
| `negative-source-conflict.json` | 同目标同轮次矛盾且来源未确认 | `INSUFFICIENT` | `CONFLICT` | EV-003 |
| `negative-different-round.json` | 用 round 1 证据核验 round 2 | `INSUFFICIENT` | `MISSING` | EO-010 |
| `negative-duplicate-observation-id.json` | 重复 ID 不填槽 | `INSUFFICIENT` | `MISSING` | EO-011 |
| `negative-empty-obligations.json` | `obligations=[]` | `INSUFFICIENT` | `MISSING` | EO-001 |
| `negative-window-missing-sample.json` | 仅 2 组 | `INSUFFICIENT` | `MISSING` | W-003 / EO-012 |
| `negative-future-timestamp.json` | `observed_at > decision_time` | `INSUFFICIENT` | `MALFORMED` | EO-009 |
| `negative-passed-but-business-false.json` | `StateVerifier.passed=true` 但业务谓词 false | `CONTRADICTED` | `[]` | EV-002 / 第 8 节 |

---

## 11. 实现边界与待核验项

### 11.1 实现阶段才创建的文件

- 本 PLAN 阶段**不创建** `agent/recovery_contracts/models.py` 与 `agent/recovery_contracts/__init__.py`。
- 待本 schema 与样例经未参与起草的独立审阅后，IMPLEMENT 阶段再按版本化流程创建：`agent/recovery_contracts/models.py`、`__init__.py`，随后 N02-N05 各自认领 evaluator/probes/scheduler/verifier/receipts/replay。
- 不新建第二审批、不改 run-event schema、不改任何既有业务文件。

### 11.2 仍为 UNKNOWN 的项

- `claim_type` 后续是否新增其他已审核值（V1 仅 `BUSINESS_RECOVERY`，新增需修订）。
- `receipt_ttl_ms` 的生产取值与合同绝对到期时间的可信登记来源。
- 生产构建是否实际设置 `VITE_AI_SERVICE_URL`；见 `routing-evidence.md`。
- Java ↔ Python 调用链未证实。
- `expires_after` 与合同登记时间的绑定方式。
