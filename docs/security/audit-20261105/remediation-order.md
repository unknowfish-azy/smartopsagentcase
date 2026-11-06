# HC-02 最小整改顺序（供后续 IMPLEMENT/RUN 认领）

- 日期：2026-11-05
- 定位：PLAN 阶段产物，只给顺序、依赖、验收与保护项；**本次不执行命令、不改代码**。
- 排序：先切断"无认证即可达"，再保证"审批即绑定"，再收缩"服务端出站"，最后处理"敏感数据与日志"。管理权限 fail-open 与资产 scope 作为认证链同批 P0/P1，避免"认证补了但权限仍全开"。
- 原则：宁可 fail-closed（拒绝/503），不为兼容放宽；每阶段可独立回滚。

## 1. 依赖关系

```
Phase 0 基线固化
   ↓
Phase 1 认证链（聊天 / Knowledge / 内部边界 / 管理 fail-closed）
   │        └─ 产出：可信 subject + run_id + 网关鉴权
Phase 2 审批绑定（Java grant / MultiExec / Agent run_id）
   │        └─ 依赖 Phase 1 的 subject/run 身份
Phase 3 爬取与出站边界（SSRF / 资源上限）
   │        └─ 可独立止血（关闭爬取开关）
Phase 4 scope 与幂等（Server/Inspector/Loop/MAX(id)）
   │        └─ 依赖 Phase 1 的团队/主体模型
Phase 5 日志、脱敏与部署默认
            └─ 依赖 Phase 1-4 字段/路由稳定
```

**可并行不可倒序**：Phase 3 的"关闭爬取"可与 Phase 1 并行止血；Phase 5 日志脱敏不得早于 Phase 2（否则审批证据被抹掉）。

## 2. Phase 1：认证链（P0）

### 1.1 目标

1. 聊天有可信主体（user/tenant/team）与服务端签发 run_id。
2. `/ai-api` 不再匿名可达；ai-service 无有效凭证拒绝。
3. Knowledge 未配置 key 时 fail-closed（或仅绑 127.0.0.1 且显式允许匿名）。
4. 管理权限不再"缺 profile 即全能力"；治理表故障不授权。

### 1.2 最小实现

- **方案 A（推荐）**：聊天仍由 ai-service 处理，但请求必须带 Java 签发的短时 token（HMAC/JWT，含 `sub/run_id/exp/scope`）；Java 创建 run 时生成，前端经 `/api` 获取，ai-service 校验签名与过期。保留 SSE。
- **方案 B**：聊天端点迁到 Java 代理，session 认证后转发到 8001；改造量大，备选。
- **nginx**：删除 `/ai-api` 公网映射；必须保留时加 `auth_request` 或仅允许内网 CIDR。
- **ai-service**：所有 `/api/chat*` 增加依赖级 `verify_run_token`；run_id 只从 token 取，忽略客户端头；`X-Request-ID` 仅 trace。
- **Knowledge**：`KNOWLEDGE_API_KEY` 缺失时启动失败（除非 `KNOWLEDGE_ALLOW_ANONYMOUS=true` 且 bind 127.0.0.1）；`ALLOW_INGEST` 永不与匿名组合。
- **管理权限**：`hasPlatformCapability` 对"无 profile 行"返回 false（迁移白名单 user_id 可一次性授予）；`createAccount`/角色提升事务内写 profile（默认空能力）；`platformAdministrators` 异常返回 500/503，不回退 root 列表。
- **内部 token**：生产断言 `smartops.security.internal-bypass=false`（`application.yml:129`），建议启动失败。

### 1.3 依赖

- HC-01 定义 subject/tenant/team 与 run 字段；N06 协同；HC-05 提供 secret 注入（不得硬编码）。

### 1.4 验收命令（未来 RUN，禁止本次执行）

```bash
mvn -q -pl backend -Dtest=ChatAuthContractTest,AdminCapabilityFailClosedTest test
pytest ai-service/tests -q -k "chat_auth or run_token"
pytest knowledge/tests -q -k "api_key_required or ingest_denied"
curl -s -o /dev/null -w "%{http_code}\n" -X POST http://127.0.0.1:8001/api/chat \
  -H "Content-Type: application/json" -d '{"message":"hello"}'   # 期望 401/403，不是 200
```

### 1.5 不可越过的保护项

- 不删除 `TrustedUserIdFilter` 的 session 覆盖；改"拒绝客户端用户头"前须先让 controller 全改用 principal。
- 不删除 `InternalTokenAuthenticationFilter` 的 503 fail-closed 与 401；生产强制 bypass=false。
- 不放宽 `anyRequest().authenticated()`；不把 `/api/**` 整体 permitAll。
- 不取消 CSRF；网关/内部路径豁免仅限非 cookie 认证。

### 1.6 回滚点

- 开关 `CHAT_REQUIRE_RUN_TOKEN`；关闭时不得回退到"匿名 200"，应回退到"仅内网可达 + 503"。
- 管理能力迁移先 deny 提升，再补 profile 数据（只读灰度）。

## 3. Phase 2：审批绑定（P0/P1）

### 2.1 目标

1. MultiExec 第二确认必须不同主体、服务端签发、绑定 preview digest、一次性、有 TTL。
2. Java run 真正校验 grant_token；digest 绑规范化参数+工具版本+审批人；审计存 digest；补取消与创建幂等键。
3. Agent fingerprint 加 run_id；legacy `create_request` 不再产生可用审批；审计落库；非只读禁止布尔旁路。

### 2.2 最小实现

- MultiExec：保留 `/preview`、`/execute`；preview 返回 `previewId + digest`，**不返回**第二确认凭据；execute 要求 `secondApproverToken`（另一主体在其会话内 `/approve` 生成），服务端条件 UPDATE 消费；并发用唯一约束/状态条件。
- Java run：`consumeGrant` 校验 `grantToken`（常量时间），digest 输入改 `canonical(parameters_json)+toolId+toolVersion+approverId`；approve 写审计含 digest；新增 `CANCELED`；审批人比较改 `Objects.equals`。
- Agent：`ApprovalContext` 增 `run_id` 并纳入 payload；`create_request` deprecated，`validate` 对无指纹审批直接 False；`approve` 记录 reviewer，宿主可提供时要求 reviewer≠requester。
- 双审批记录统一走 HC-01 "审批轴"字段，避免三套语义。

### 2.3 依赖

- Phase 1 可信 subject；HC-01 审批表结构；HC-07 审计表。

### 2.4 验收命令（未来 RUN）

```bash
mvn -q -pl backend -Dtest=TeamRunGrantBindingTest,MultiExecSecondApproverTest test
pytest agent/tests -q -k "approval_run_binding or approval_replay"
# 负例：同一 nonce 自批 409；无 grantToken 409；并发 execute 仅 1 次 200
```

### 2.5 不可越过的保护项

- 保留 `TeamAgentRunService.java:201-203` 条件 UPDATE 原子消费，不得"先查后改"。
- 保留 approve 前必须 preview 且 `previewed_by == approver`。
- 保留 `ApprovalManager.validate(consume=True)` 一次性消费，不得关闭 consume 以便重试。
- 保留 `PolicyEngine` 对非只读工具的审批强制，不得为体验放开只读判断。

### 2.6 回滚点

- MultiExec 可配置降级为"单审批 + 强提示"，但 **CRITICAL 必须硬拒绝**，不得静默放行。
- grantToken 导致旧客户端失败时，发布前双写 token 字段并一次性迁移；不要回退为无 token。

## 4. Phase 3：爬取与出站边界（P0）

### 3.1 目标

1. 统一 URL 安全校验：scheme 白名单、host 规范化（尾点/IDN）、DNS 解析、IP 分类（私网/回环/链路本地/ULA/CGNAT/组播/保留）、IPv4-mapped IPv6。
2. 连接期 pin 已校验 IP（或每跳/每连接复检），禁 DNS rebinding。
3. 首跳与每跳复检（含历史 seed、队列链接）。
4. 响应体上限（建议 10MB，可配置）、Content-Length 预检、总超时、单用户并发/速率。
5. 模型连接 baseUrl 复用同一校验（SEC-14）。

### 3.2 最小实现

- 抽 `OutboundUrlPolicy`：解析 host → `InetAddress.getAllByName` → 所有地址必须在 allowlist；尾点先去除再判断。
- `HttpClient` 固定 IP 连接或自定义 `ProxySelector`（显式禁用系统/环境代理），保留 `followRedirects(NEVER)`。
- `fetch()` 首跳调用 `publicTarget`；`run()` 入队前再校验 DB seed。
- `BodyHandlers.ofInputStream` + 读取上限 + 超时；maxPages/每页 sleep/全局并发信号量。
- 迁移期开关：`KNOWLEDGE_CRAWL_ENABLED=false` 默认关闭，清理/禁用历史 source。

### 3.3 依赖

- 可与 Phase 1 并行；DNS 校验复杂时先"关闭爬取"止血；与 HC-04 协同。

### 3.4 验收命令（未来 RUN）

```bash
mvn -q -pl backend -Dtest=OutboundUrlPolicyTest,CrawlSsrfTest,CrawlResourceLimitTest test
# 全部指向本地 mock（127.0.0.1:18080），禁止外网
```

### 3.5 不可越过的保护项

- 保留 `followRedirects(NEVER)` 与最多 4 跳手写循环。
- 保留 `extractLinks` 同 seedHost 限制（额外收紧，不是阻碍）。
- 不得只扩大字符串黑名单；不得以"内网可信"跳过每跳校验。
- 不得把超时/上限放宽到现有 8s/50 页之上而无审计理由。

### 3.6 回滚点

- 回退为"爬取全禁"，不是"校验放宽"；已有 source 保留只读列表，禁止 run。

## 5. Phase 4：scope 与幂等（P1）

### 4.1 目标

1. Server/Inspector 读侧按 team/owner 过滤；全局视图仅审计管理员可读且留审计。
2. `inspector_event` 增归属（user/team/source system），可选迁移。
3. 闭环同步只消费当前用户可见事件；`(user_id, source_type, source_ref)` 唯一约束 + upsert。
4. review 幂等；learn 以 `(source_ref, lesson_hash)` 去重。
5. 创建返回主键改 `GeneratedKeyHolder`/`RETURNING`，移除 `MAX(id)`。

### 4.2 依赖

- Phase 1 subject/team 模型；HC-01 迁移脚本与历史重复数据清理。

### 4.3 验收命令（未来 RUN）

```bash
mvn -q -pl backend -Dtest=CrossTenantReadTest,DecisionLoopIdempotencyTest,CreateReturnsOwnRowTest test
```

### 4.4 不可越过的保护项

- 不把"全局可见"作默认兼容；过渡期必须只读 + 审计。
- 唯一约束上线前完成重复数据盘点，禁止直接失败启动。

## 6. Phase 5：日志、脱敏与部署（P1/P2）

### 5.1 目标

1. 写库/回显前统一脱敏（stdout/stderr、evidence、crawl 正文与错误、tool_calls）。
2. 日志禁记 Prompt/message、请求头、Cookie、Authorization、口令、工具原文。
3. 部署默认口令/端口整改；Redis requirepass；prod 禁空密码默认。
4. 审计日志记录认证拒绝、审批通过/拒绝、scope 拒绝、SSRF 阻断，字段脱敏。

### 5.2 最小实现

- 共享 `SensitiveDataRedactor`：覆盖 `password|passwd|secret|token|api[_-]?key|authorization|cookie|private_key|session`，支持 `key=value`、`key: value`、`Bearer`、JSON；base64/多行保守处理。
- `JdbcOperationRunRecorder` 入库前 redact；`OperationRunQueryService` 返回前兜底。
- 爬取只存正文与去 query 的 URL；`last_error` 只存错误码+类名。
- 历史数据一次性清洗（先备份），默认最近 N 天（HC-07 定）。
- compose env 必填、不发布 3306/6379（或仅内网）；prod 空密码启动失败。

### 5.3 依赖

- Phase 2 完成后再清洗历史审批/证据；日志格式变更与 HC-05 发布窗口对齐。

### 5.4 验收命令（未来 RUN）

```bash
mvn -q -pl backend -Dtest=OperationOutputRedactionTest,LogNoSecretTest test
pytest knowledge/tests -q -k "log_redaction"
rg -n "Bearer |password=|api_key=" backend/logs   # 样例期望 0 命中
```

### 5.5 不可越过的保护项

- 不得为排障把 Prompt/工具原文提升到 INFO；需要时本地临时 DEBUG 且默认关。
- 不得删除安全审计日志（认证/审批/scope/SSRF），只能脱敏。
- 不得把管理口令放 query 或日志；`X-Admin-Password` 保持 header。

## 7. 最小集（只能做 5 件事时）

1. 关闭 `/ai-api` 匿名公网入口，聊天加 run token。
2. 管理权限"缺 profile 即全能力"改 false + 建号写 profile。
3. MultiExec 第二确认改不同主体 + 一次性。
4. 爬取统一 IP 校验 + 首跳复检 + 下载上限。
5. 工具输出写库前脱敏。

以上覆盖全部 P0 主体（SEC-01/02/03/06/07），不依赖大规模数据迁移。

## 8. 统一门禁

- 进入下一阶段前，必须通过本阶段负例（`test-matrix.md` 对应 TM）与现有保护回归（TM-05/06/12/14/15）。
- 每个 PR 说明：改了哪个轴（动作/纠察/恢复/授权）、是否改变 fail-closed 语义、回滚方式。
- 未验证项保持 UNKNOWN，不得写成"已修复"。
- 审计中途 ai-service 源码被移出主工作树；Phase 1 开工前先确认最终文件路径，否则阻塞。

## 9. 执行记录（2026-11-06）

本次只做代码与单元测试，**未启动 Java/ai-service/MySQL/Redis/nginx，未做 HTTP 或网络级验证**。

| 项 | 结果 | 证据 |
| --- | --- | --- |
| 1.2 方案 A：Java 签发短时 run token | 已实现 `RunTokenService`（HMAC-SHA256，`sub/run/iat/exp`）+ `GET /api/chat/run-token`（会话认证、`no-store`） | `RunTokenServiceTest` 6 pass；`ChatRunTokenController` |
| ai-service 校验 | 所有 `/api/chat*` 依赖 `verify_run_token`；run_id 只取令牌；未配密钥 503、缺失/无效/过期 401、复用 409 | `ai-service/app/tests/test_chat_auth.py` 8 pass |
| 前端保持 SSE | `fetchChatRunToken()` → `streamChat(..., {runToken})` → `X-Run-Token` | `stream-resilience.test.mjs` 20 pass（含 2 条令牌用例） |
| 1.5 爬取 SSRF | `OutboundUrlPolicy` + 首跳/逐跳/重定向复检、禁代理、10MB 下载上限、60s 总预算 | `OutboundUrlPolicyTest` 8 pass；`KnowledgeCrawlServiceTest` 3 pass |
| 内部 token 生产断言 | `SecurityAssertions` + `ApplicationRunner`：生产下 bypass/缺 token/弱 token/缺聊天机密 → 启动失败 | `SecurityAssertionsTest` 7 pass |
| SEC-03 双人确认 | 预览绑定 `ownerId`+TTL+条目上限；`requiredApprovals>1` 且执行者=预览者 → 409 `SECOND_APPROVER_REQUIRED`；过期 409 `PREVIEW_EXPIRED`、超限 429 `PREVIEW_LIMIT_EXCEEDED`、成功执行后重放 404 | `MultiExecServiceTest` 6 pass |
| SEC-07 治理 fail-closed | 缺档案仅最小只读；`platformLevel` 缺档案=null；治理表故障 500；新建/提升 admin 显式建档（deputy 无能力）；bootstrap 首 root 显式授全能力；5 个集成测试种子改用 `TestPlatformProfiles.grantRoot` 显式建档（AdminFoundation/Registration/TeamWorkspace/UserAuthentication/AdminMfa） | `UserAccountGovernanceIntegrationTest` 6 pass；4 个受影响回归类 70 pass；`AdminMfaIntegrationTest` 17 pass |
| 回归 | SEC-03 单测 6/6 通过；integration 包 158/158、后端全量 708 项 0 失败 0 错误（1 skipped）；首轮全量曾出现 16 项 AdminMfa 403（该测试种子管理员缺治理档案，已补显式建档后复跑全绿）；Python 309 pass | 2026-11-06 |
| 2.2 SEC-05 grant 绑定 | `consumeGrant` 校验 `grant_token`（`MessageDigest.isEqual` 常量时间）并作为条件 UPDATE 的 WHERE 条件；只读运行也持一次性 token；审批写 `grant_digest = SHA-256(规范化参数 + toolId + 工具版本 + 审批人)` 并审计；新增 `CANCELED` 与 `cancel` 接口；`create` 支持 `idempotencyKey`（唯一索引兜并发）；预览人比较改 `Objects.equals` | `TeamAgentRunServiceTest` 11 pass（缺 token 409、错误 token 403、篡改参数 409、幂等、撤回、高 user id 审批）；`TeamAgentRunRecoveryTest` 5 pass | 2026-11-06 |
| 回归（SEC-04/05/09 后） | 后端全量 `mvn test` 715 项 0 失败 0 错误（1 skipped，124 个测试类）；Python `tests/agent` 88、ai-service 86 | 2026-11-06 |
| 4.1 SEC-08 scope 收敛 | `server.owner_id`（V20261106.21）：创建归属本人、列表/详情/指标按属主、历史 NULL 仅 `admin.audit` 并审计；`inspector_event.user_id`（V20261106.20）：读侧按归属、全局视图仅 `admin.audit` 并审计、闭环只消费归属事件；新增 `CurrentSessions` 统一从会话主体取身份 | `ServerServiceTest` 6 pass（含他人资产 404、历史行仅审计管理员、列表按属主）、`ServerControllerTest`、`ServerMetricControllerTest`、`DecisionLoopServiceTest`（含全局/他人事件不投影）、`InspectorControllerTest` 通过 |
| 4.1 SEC-09 创建返回主键 | `PersonalKnowledgeService.createLibrary/createEntry`、`OperatorMemoryService.recordConfirmed/recordLearned`、`KnowledgeCrawlService.createSource` 改用 `GeneratedKeyHolder`，删除 `MAX(id)` 反查 | `OperatorMemoryServiceTest`（含 8 线程并发各返回自己那行）、`PersonalKnowledgeServiceTest`、`KnowledgeCrawlServiceTest`、`DecisionLoopServiceTest` 通过 |
| 2.2 SEC-04 Agent run 绑定 | 执行指纹 payload 新增 `run_id`；`create_for_step` 要求 run 身份；`create_request` 标记 Deprecation（仅信息记录、永不授权）；`approve` 拒绝 reviewer=requester | `tests/agent/test_execution_approval.py` 42 pass；`tests/agent` 88 pass；ai-service 86 pass | 2026-11-06 |

**仍未完成（不得声称已修复）**：
- SEC-04/05 仅到代码 + 单元测试：`/api/team-agent-runs/*/execute` 的缺 token / 错误 token / 篡改参数负例未做 HTTP 级验收（`NOT_RUN`）。
- Python 审批仍为进程内状态，无持久化审批审计表；宿主 reviewer 身份认证仍由调用方负责。
- nginx `/ai-api` 网络层隔离未实施，仅保留应用层 401（注释已标注）。
- 连接期 IP pin 未实现，DNS rebinding 仍为残余风险。
- 爬取并发上限（TM-25）、slow-drip（TM-23）未验证。
- TM-01/02/03/18-24 的 HTTP/网络级验收全部 `NOT_RUN`。
