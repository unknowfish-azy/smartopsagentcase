# N06 平台接入映射与阻断条件（PLAN）

- 日期：2026-11-05
- 状态：**平台侧读写接口已实施（2026-11-06）；端到端仍 `NOT_RUN`**。§3 的映射已在 backend 落地（见 §8）；Python 写入方尚未调用，真实 E2E 未跑，对外仍只讲接口与隔离机制。
- 依据：[原创创新任务包 §10](../development/原创创新AI任务包-20261105.md)、[交接书](../development/SmartOpsAgent-全面整改与创新升级交接书-单文件版-20261105.md)、[HC-00 基线](../audit/20261105/status-baseline.md)

## 1. 现状盘点

| 环节 | 代码位置 | 事实 |
|---|---|---|
| Inspector 写入 | [InspectorController.java](../../backend/src/main/java/com/smartops/controller/InspectorController.java#L38-L54) → [InspectorEventService.java](../../backend/src/main/java/com/smartops/service/InspectorEventService.java#L84-L137) | `POST /api/inspector/{check,verify,replan}` 写 `inspector_event` / `inspector_issue` / `inspection_evidence` / `inspection_verification` |
| 内部鉴权 | [InternalTokenAuthenticationFilter.java](../../backend/src/main/java/com/smartops/security/InternalTokenAuthenticationFilter.java#L32-L78)、[SecurityConfig.java](../../backend/src/main/java/com/smartops/config/SecurityConfig.java#L31) | 写接口走 `X-SmartOps-Internal-Token`；存在 `internal-bypass` 开发开关 |
| 状态核验原值 | `InspectorEventService.saveVerification`（同文件 L177-L186） | `inspection_verification.resolved` 保存布尔原值，`details_json` 自由 JSON |
| Run 相关 ID | [RunCorrelationFilter.java](../../backend/src/main/java/com/smartops/operations/RunCorrelationFilter.java#L26-L36) | `X-Request-ID` / `X-Task-ID` / `X-Run-ID` 仅进入 MDC 与响应头，**不校验归属** |
| Run 权威 | `local-schema.sql` L19-L21、[JdbcOperationRunRecorder.java](../../backend/src/main/java/com/smartops/service/JdbcOperationRunRecorder.java#L40-L85) | `operation_run_record(id, trace_id, user_id, idempotency_key, status, deadline_at…)`；幂等键按用户唯一；查询按 `user_id` 过滤 |
| 执行证据 | `operation_run_evidence(run_id, evidence_type, content, source_ref)` | 已有通用证据表，可承载“契约/回执摘要引用”，不宜塞入敏感正文 |
| Inspector 管道 | [agent/inspector/pipeline.py](../../agent/inspector/pipeline.py#L66-L105) | `InspectorPipeline.run` 产出 `InspectionResult`；`verification_result.passed` 只作为纠察轴原值 |
| 运行事件 | [agent/runtime_events.py](../../agent/runtime_events.py#L11-L36) | `RunIdentity`/`terminal_event` 生成 run 级事件，不保存请求正文 |

结论：平台内已有 **Run 权威**（`operation_run_record`）与 **Inspector 记录链**；恢复契约应**引用**它们，而不是新建第二套 Run 或审批源。

## 2. 身份与权威规则（接入前必须成立）

1. 主体只来自认证上下文（Session/`SessionUser`），客户端传入的 `X-User-Id`、`team_id`、`run_id`、`contract_id` 仅作查询键，不授予所有权。
2. 契约必须绑定一个已存在的 `operation_run_record.id`；创建/查询/回执读取都按 `user_id` 过滤，跨用户一律 404/403，不泄露存在性。
3. 幂等：同一用户 + 同一 `idempotency_key` 的写请求不得重复签发回执（参考 `JdbcOperationRunRecorder.start` 的 409 语义）。
4. `X-Run-ID` 保持“相关 ID”定位，不得作为恢复回执的签发依据。

## 3. 接入映射（已实施，见 §8）

| 恢复对象 | 平台落点 | 规则 |
|---|---|---|
| `RecoveryContract` | 新表 `recovery_contract_record`（`run_id` 外键 → `operation_run_record`，含 `digest`、`scope`、`target`、`expected_revision`、`valid_from`） | 写入前校验 run 归属；不改 run 表结构 |
| `Claim` | 同表列或 `details_json` | 必须绑定 `contract.digest` |
| `EvidenceObservation` | 新表 `recovery_observation_record`（`contract_id`、`probe_id`、`source_group`、`observed_at`、`artifact_digest`） | 由 Python 探针经内部 token 写入；原始 payload 不入 run-event |
| `VerificationReceipt` | 新表 `recovery_receipt_record`（`contract_id`、`receipt_state`、`valid_until`、`evidence_snapshot_digest`） | 非 `VERIFIED` 强制 `NOT_ISSUED`、时间字段 null |
| 回执/契约引用 | `operation_run_evidence(evidence_type='RECOVERY_RECEIPT_REF', source_ref=receipt_id)` | 只存引用与摘要，不复制正文 |
| StateVerifier 原值 | `inspection_verification.resolved` 保持不变 | 恢复判定单独一列/一表，不用 `resolved` 替代 |

读接口（拟议，复用现有鉴权）：

- `GET /api/runs/{runId}/recovery` → 契约 + 回执 + 缺口（按当前用户过滤）。
- `POST /api/runs/{runId}/recovery/contracts` → 创建契约（幂等键必填）。
- `GET /api/recovery/contracts/{contractId}/replay` → 回放结果（只读）。
- 探针写入仍走内部 token 端点，不开放给浏览器。

## 4. 阻断条件（当前状态）

| 条件 | 现状 | 解除方式 |
|---|---|---|
| Java 17 + Maven 可构建 | **已通过**：`mvn -DskipTests compile` 成功；`mvn test` 579 项（0 fail / 1 skip） | 已解除 |
| 内部 token 已配置 | 未验证；默认空值会返回 503 | 部署侧注入 `smartops.security.internal-token`，禁用 `internal-bypass` |
| 认证与越权修复 | SEC-01/02/06 未修 | 按安全整改顺序先修 P0 |
| 持久化迁移与回滚 | 未编写迁移 | 先备份副本，迁移仅前向；回滚脚本随迁移提交 |
| 真实平台 E2E | 未执行（本会话不启动服务） | 通过前述门禁后录浏览器/网络/run_id 证据 |

### 4.1 构建环境探测（2026-11-05）

- 默认 `java` 仍是 1.8.0_202；scoop 的 `openjdk21` 不可用（启动报 Windows 兼容错误）。
- scoop 存在 `openjdk17 17.0.2-8`：设置 `JAVA_HOME=C:\Users\33908\scoop\apps\openjdk17\current` 后 `java -version`、`mvn -v` 均正常（Maven 3.9.15，Java 17.0.2）。
- 因此“缺少 JDK 17”不再是阻断原因；剩余阻断是代码编译错误与后续门禁。
- 复现命令：

```powershell
$env:JAVA_HOME='C:\Users\33908\scoop\apps\openjdk17\current'
mvn -B -DskipTests compile
```

当前结果：`BUILD SUCCESS`；`mvn test` 579 项通过（0 fail / 1 skip）。`OperationRunController` 的缺失 import 已由并行任务在 22:37 修复，本会话未改动该文件。

## 5. 验收用例（接入后必须逐条有原始记录）

| # | 用例 | 预期 |
|---|---|---|
| 1 | 用户 A 读用户 B 的 `runId`/`contractId` | 404/403，不泄露存在性 |
| 2 | 同一幂等键重复创建契约 | 第二次 409，不重复签发 |
| 3 | 服务重启后读回执 | 从持久表读取，状态与 `valid_until` 一致 |
| 4 | 回执已过期/`REVISION_CHANGED` | 当前视图失效，历史可审计 |
| 5 | Inspector 判违规但契约全 TRUE | 两个状态轴分别展示，不被契约 VERIFIED 覆盖 |
| 6 | `StateVerifier.passed=false` | 原值完整保存；不影响恢复轴判定路径 |
| 7 | 客户端自报 `X-Run-ID` 指向他人 run | 拒绝，不以头部授予权限 |
| 8 | 回放缺录制探针 | `REPLAY_INCOMPLETE`，不补探 |

以上 8 项目前均为 `NOT_RUN`。

## 6. 回滚

1. 迁移前对数据库文件做带时间戳副本，记录前后 hash 与行数。
2. 新增表可回滚为“删除新增表 + 移除引用列”，不改既有 `operation_run_*` 结构与数据。
3. 代码回滚按文件清单逐个恢复；不使用 `git reset --hard`、不覆盖并行 AI 改动。

## 7. 结论

N06 的平台侧接口已落地：契约/观测/回执/回放包四张表、按主体过滤的只读接口、仅内部 token 可用的写入接口、前端 `/operations/recovery` 真实数据页。剩余阻断是 **Python 写入方接入与真实 E2E**，因此对外口径为"接口与隔离机制已就绪，闭环未验证"，不宣称已接入生产。

## 8. 实施记录（2026-11-06）

### 8.1 已落地

| 层 | 内容 |
|---|---|
| 迁移 | [V20261105.11__recovery_contract.sql](file:///d:/SmartOpsAgent/backend/src/main/resources/db/migration/V20261105.11__recovery_contract.sql)：`recovery_contract_record` / `recovery_observation_record` / `recovery_receipt_record` / `recovery_replay_bundle_record`，全部新增表，不改既有 `operation_run_*` |
| 读接口 | `GET /api/recovery/contracts`、`GET /api/recovery/contracts/{id}`、`GET /api/recovery/contracts/{id}/replay`；主体只取 `SessionUser`，越权一律 404 |
| 写接口 | `POST /api/internal/recovery/contracts`、`/{id}/observations`、`/{id}/receipts`、`/{id}/replay-bundles`；仅 `X-SmartOps-Internal-Token`，未配置 fail-closed 503 |
| 准入校验 | run 归属必须与 `ownerUserId` 一致；幂等键与观测 ID 唯一；非 `VERIFIED` 回执强制 `NOT_ISSUED` 且时间为 null（semantics §7）；变形回放包不得标为历史事实 |
| 前端 | 页面 [RecoveryContractsView.vue](file:///d:/SmartOpsAgent/frontend/src/views/operations/RecoveryContractsView.vue) 默认真实数据；空表显示明确空态；演示样例独立切换并保留 fixture 横幅 |

### 8.2 验收用例状态

| # | 用例 | 状态 |
|---|---|---|
| 1 | 越权读他人契约 | **已覆盖**：`RecoveryContractIntegrationTest#detailHidesOtherUsersContract`（404） |
| 2 | 同一幂等键重复创建 | **已覆盖但口径细化**：同 digest 幂等重放返回 200 与原 id（不重复签发）；同键不同 digest 返回 409。与 §5 原"第二次 409"预期不同，此处明示偏差，未静默放宽 |
| 5 | 双轴并列 | **已覆盖**：适配层保持 `inspection_passed=null`，不用契约 verdict 覆盖纠察轴 |
| 7 | 客户端自报身份 | **已覆盖**：读接口不读 `X-User-Id`；内部写接口缺/错 token 分别 401/403 |
| 3 | 服务重启后读回执 | `NOT_RUN`（表持久化已具备，未做实机重启验证） |
| 4 | 回执过期/失效 | `NOT_RUN`（失效事件写入方未接入） |
| 6 | `StateVerifier.passed=false` 原值 | `NOT_RUN`（纠察轴仍在既有 `inspection_verification`，本接口未改动） |
| 8 | 回放缺探针 → `REPLAY_INCOMPLETE` | `NOT_RUN`（结论由 Python 回放方给出，平台只存结果） |

### 8.3 验证

```powershell
# backend（JAVA_HOME=openjdk17，单 Maven 进程）
mvn test
[WARNING] Tests run: 620, Failures: 0, Errors: 0, Skipped: 1
[INFO] BUILD SUCCESS

# frontend
npm test        # tests 492 / pass 492 / fail 0
npm run typecheck   # 通过
npm run build      # ✓ built in 11.07s
```

### 8.4 回滚

`git revert` 对应提交即可；迁移只新增表，代码回滚后遗留空表不影响运行，需要彻底清理时按 §6 删除四张新表。

