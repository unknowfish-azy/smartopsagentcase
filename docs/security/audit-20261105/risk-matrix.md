# HC-02 安全与权限审计 — 风险矩阵（静态只读基线）

- 审计日期：2026-11-05
- 审计方式：仅静态阅读代码与配置；**未启动服务、未做故障注入、未连接真实数据库、未对任何真实第三方发起探测**。下列风险均为"可由代码推导的缺陷假设"，不等同于已在运行环境利用成功。
- 基线复用：`docs/audit/20261105/route-map.md`、`docs/audit/20261105/status-baseline.md`；本文件与二者不矛盾，只补充安全视角。
- 优先级：P0 = 认证缺失、审批绕过、命令执行或全量管理员权限；P1 = 跨主体读取、审批/审计语义不完整、敏感数据落库；P2 = 纵深防御与配置硬化。
- 状态：`静态确认` = 代码路径已核实；`UNKNOWN` = 依赖部署/运行时，未验证；`BLOCKED` = 缺本地 fixture，本次无法验证。
- 归属：HC-01（核心决策/数据模型）、HC-02（本任务）、N06（聊天主链路）、HC-04（知识）、HC-05（部署）、HC-07（闭环/记忆）。
- 工作树说明：审计开始时 `ai-service/app/**` 源文件可读，审计中途该目录被并行改动移出主工作树（当前仅剩 `__pycache__`）。本文 ai-service 行号以审计时快照为准；Java/前端/部署/知识侧行号已按当前工作树复核。IMPLEMENT 前请重新核对 ai-service 路径与行号。

## 0. 必须保留的现有保护（不得在整改中删除或弱化）

1. `TrustedUserIdFilter.java:18-28`：已认证且 principal 为 `SessionUser` 时用 session 用户覆盖 `X-User-Id`，防止客户端直接指定主体。
2. 内部 token 过滤：`InternalTokenAuthenticationFilter.java:33-43` 仅对 `/api/model-connections/*/runtime|invoke` 与 `/api/inspector/check|verify|replan` 生效（`SecurityConfig.java:31`）；`InternalTokenAuthenticationFilter.java:56-59` token 未配置返回 503（fail-closed），`X-SmartOps-Internal-Token` 缺失/错误返回 401，且不授予 session 权限。`smartops.security.internal-bypass` 默认 false（`application.yml:129`），开启即跳过校验，属部署红线。
3. `AdminConfirmationFilter.java:23-37`：管理端写操作需 `X-Admin-Password` 二次确认（CSRF 由全局 CSRF 过滤器另行校验）。
4. `TeamAgentRunService.java:195-203` grant 消费为条件 UPDATE（`APPROVED` → `RUNNING`），`changed != 1` 返回 409，保证一次性消费的数据库原子性；审批前强制 `markPreview` 且 `previewed_by == approver`（`148-168`），禁止预览人自批。
5. Agent `ApprovalManager` 已有执行指纹（request/user/environment/step/tool/action/arguments）与一次性消费：`agent/safety/approval.py:73-91`、`93-113`；`PolicyEngine.authorize_execution` 对非只读工具强制校验：`agent/policies/policy_engine.py:69-76`。
6. `SecurityConfig.java:52-62` 默认 `anyRequest().authenticated()`，permitAll 仅健康检查、匿名会话、内部 token 路径、OpenAI 兼容网关；网关自身校验 Bearer key（`ModelGatewayController.java:167-193`）。
7. 终端 WebSocket：`AuthenticatedSessionHandshakeInterceptor.java:18-28` 校验 session，`OperationsTerminalWebSocketHandler.java:62-72` 再次校验用户/账号状态/MFA，Origin 仅 localhost（`OperationsWebSocketConfig.java:18-22`；生产域名 UNKNOWN）。
8. `KnowledgeCrawlService.java:188-195` 已禁用自动重定向并手写最多 4 跳、逐跳调用 `publicTarget`，是 SSRF 整改的既有基线。

## 1. 风险总表

| ID | 优先级 | CWE | 简述 | 归属 |
| --- | --- | --- | --- | --- |
| SEC-01 | P0 | CWE-306 / CWE-639 | ai-service 聊天主链路无身份校验，经 nginx `/ai-api` 对公网可达 | N06 / HC-01 |
| SEC-02 | P0 | CWE-345 / CWE-639 | `X-Run-ID` 客户端任意指定，与主体/Java run 无绑定 | N06 / HC-01 |
| SEC-03 | P0 | CWE-345 / CWE-367 | MultiExec 双人确认用同一 nonce，等于自批；并发可重复执行 | HC-02 / HC-01 |
| SEC-04 | P1 | CWE-294 / CWE-384 | Agent 审批未绑定 run_id，可跨 run 复用；legacy 审批无指纹/无过期 | HC-02 / HC-07 |
| SEC-05 | P1 | CWE-345 / CWE-613 | Java grant 的 digest 只绑渲染命令，token 生成但从不校验，无取消与幂等键 | HC-02 / HC-01 |
| SEC-06 | P0 | CWE-918 | 爬取 SSRF：仅字符串黑名单、无 DNS/IP 固定、IPv6/映射/尾点绕过、首跳不复检、无下载上限 | HC-02 |
| SEC-07 | P0 | CWE-269 / CWE-863 | 无 `platform_admin_profile` 的 admin 被视为全能力 ROOT；新建/提升 admin 不写 profile | HC-02 |
| SEC-08 | P1 | CWE-639 / CWE-284 | Server/Inspector 查询无统一 scope；全局 inspector 事件被投影进每个用户闭环 | HC-01 / HC-02 |
| SEC-09 | P1 | CWE-362 | `MAX(id)` 取刚插入 ID，同 owner 并发下可能返回同用户他人记录 | HC-01 |
| SEC-10 | P1 | CWE-837 / CWE-362 | 重复 review/GET 同步重复 learn 与 memory feedback，置信度/证据被放大 | HC-01 / HC-07 |
| SEC-11 | P1 | CWE-532 / CWE-312 | 工具 stdout/stderr、爬取正文与错误、巡检证据、管理口令头等敏感面落库/落日志且未统一脱敏 | HC-02 / HC-05 |
| SEC-12 | P1 | CWE-306 | Knowledge `/api/search` 仅在配置 KEY 时校验，默认开放；`ALLOW_INGEST=1` 匿名可写 | HC-04 / HC-02 |
| SEC-13 | P1 | CWE-798 / CWE-1188 | 部署默认口令与端口发布（MySQL root/change-me、Redis 0.0.0.0:6379 无 requirepass、本地固定 AES key） | HC-05 |
| SEC-14 | P2 | CWE-918 | 模型连接 baseUrl 任意 http(s)，无内网限制（调用入口受内部 token 保护） | HC-02 |
| SEC-15 | P2 | CWE-639 / CWE-807 | 内部 token 仅覆盖 5 条路径；`X-User-Id` 仍被多处 controller 直接读取；`internal-bypass` 开关可关鉴权 | HC-01 / HC-02 |

## 1.1 本次修复状态（2026-11-06，代码 + 单测，未启动服务）

| ID | 状态 | 已落地 | 残余 |
| --- | --- | --- | --- |
| SEC-01 | 已修（应用层 + 网络层） | 新增 `RunTokenService` + `GET /api/chat/run-token`；ai-service 所有 `/api/chat*` 依赖校验 HMAC/过期；未配密钥 503、匿名 401；nginx `/ai-api/` 加回环+私网 CIDR allowlist（公网 403）；compose 不再发布 ai-service 8001（仅 nginx 与容器网络可达） | 同源 `/ai/` 仍是公网入口，只靠应用层令牌（无令牌 401）；上层负载均衡若以私网地址回源，`allow` 网段会被视为内网（需网络 ACL 补足）；`nginx -t` 未运行（镜像/守护进程不可用） |
| SEC-02 | 已修 | run_id 只取签名令牌；客户端 `X-Run-ID` 被忽略；同一令牌复用 409 `RUN_TOKEN_REPLAYED`；令牌绑定 subject | 令牌单进程内存去重，多副本部署需共享存储 |
| SEC-06 | 已修（代码级） | `OutboundUrlPolicy`：尾点/IDN/大小写归一，DNS 全地址分类（IPv4 私网/CGNAT/保留、IPv6 ULA/链路本地/映射/文档网段），首跳与逐跳复检，禁系统代理，下载 10MB 上限，单 run 60s 预算 | 未做连接期 IP pin；无并发上限（审计 TM-25 未覆盖）；未见真实 DNS rebinding 注入 |
| SEC-15 | 已修（启动断言） | `SecurityAssertions` + `SecurityAssertionConfig`：生产（profile prod/production 或显式开关）下 `internal-bypass=true`、内部 token 缺失/过短、聊天令牌机密缺失 → `SECURITY_ASSERTION_FAILED` 拒绝启动；非生产仅告警 | `X-User-Id` 直读未收敛；内部 token 仍只覆盖 5 条路径；断言需真实启动一次才能观测（当前 `NOT_RUN`） |
| SEC-03 | 已修（代码级） | 预览绑定创建者（`ownerId`）+ TTL（默认 15min，`preview-ttl-ms`）+ 条目上限（默认 200，`preview-max-entries`，超限 429 `PREVIEW_LIMIT_EXCEEDED`）；过期预览执行 → 409 `PREVIEW_EXPIRED`；`requiredApprovals>1` 时执行者=预览者 → 409 `SECOND_APPROVER_REQUIRED`（回显同一 nonce 不构成第二人复核） | 主体仍取 `X-User-Id`（SEC-08 收敛后绑定才完全可信）；无持久化审批记录 |
| SEC-04 | 已修（代码级） | 执行指纹 payload 纳入 `run_id`，跨 run 复用审批直接 False；`create_for_step` 要求 run 身份（缺失 fail-closed）；legacy `create_request` 标记 Deprecation 且无指纹/无过期，永不授权；`approve` 拒绝 reviewer=requester | 审批仍为进程内 `_records`，重启即丢、无持久化审计；reviewer 身份认证仍由宿主负责；`SafeAgent` 布尔旁路无生产调用方，未改 |
| SEC-05 | 已修（代码级） | `consumeGrant` 校验 `grant_token`（`MessageDigest.isEqual` 常量时间）并作为条件 UPDATE 的 WHERE；只读运行也持一次性 token；审批写 `grant_digest`（规范化参数+toolId+工具版本+审批人）并记入审计；新增 `CANCELED`/`cancel` 与创建幂等键；预览人比较改 `Objects.equals`（修复 >127 user id 误判） | HTTP 级负例（缺/错 token、篡改参数）`NOT_RUN`；cancel 仅 API，界面未接入；历史库中只读运行的 NULL token 不再可执行（需重新创建） |
| SEC-08 | 已修（代码级，属主模型） | `server` 新增 `owner_id`：创建归属本人，列表/详情/指标按属主过滤；历史 NULL 行仅 `admin.audit` 可读并留审计（`PLATFORM_INFRA_VIEW`）。`inspector_event` 新增 `user_id`：普通用户只读自己的事件，内部通道事件为 NULL，全局视图仅 `admin.audit` 并留审计（`INSPECTOR_GLOBAL_READ`）；闭环同步只消费 `user_id = 当前用户` 的事件 | 历史 server 行（`owner_id NULL`）普通用户不可见，需一次性归属迁移；`X-User-Id` 仅收敛到 Server/Inspector 链路，其余 controller 仍依赖 `TrustedUserIdFilter` 覆盖；指标子资源仅校验资产归属 |
| SEC-09 | 已修（代码级） | 创建库/条目（`PersonalKnowledgeService`）、记忆（`OperatorMemoryService.recordConfirmed/recordLearned`）、爬取 source（`KnowledgeCrawlService.createSource`）全部改为 `GeneratedKeyHolder` 返回本次插入主键，移除 `MAX(id)` 反查 | 其余服务（backup drill / artifact draft / iac apply / sentinel silence）仍有同形态 `MAX(id)`，未在本批处理；无 MySQL 级并发验证（H2 8 线程用例通过） |
| SEC-10 | 已修（代码级） | `review` 改为条件 UPDATE 原子认领学习（`WHERE ... AND NOT(stage='LEARNED' AND outcome=?)`），同结论重复/并发 review 不再重复 `learn`、不累加 `learned_count`、不放大置信度；结论翻转仍可再学习。`syncFromInspector` 的 `NOT EXISTS` 按 `(user_id, source_type, source_ref)` 对齐，配合迁移唯一键 `uq_agent_decision_loop_user_source`，并捕获 `DuplicateKeyException` 跳过，杜绝并发 GET 重复闭环与 500 | `operator_memory` 无 `source_refs` 唯一键，跨服务重复沉淀仍可能；无 MySQL 级并发验证（H2 用例覆盖重复 review 与 8 线程同步） |
| SEC-07 | 已修（代码级） | `hasPlatformCapability` 缺档案 → 仅 `MINIMAL_READ_ONLY_CAPABILITIES`（admin.audit/teams.view/teams.audit），其余 403；`platformLevel` 缺档案 → null；治理表故障 → 500 fail-closed（不再把全部 admin 当 root）；`createAccount`/提升为 admin 显式建档（deputy、无能力）；bootstrap 首管理员显式授 root+全能力 | 历史部署中未经迁移回填的无档案管理员将失去写能力（迁移 V20261005 已回填，需确认执行）；SEC-08 的 `X-User-Id` 收敛未做 |
| SEC-11 | 已修（代码级） | `OperationRedactor` 扩展为统一脱敏：`key=value` / `key: value` / JSON 引号值 / `Bearer` / PEM 私钥块 / `Cookie`（键名覆盖 password/token/secret/api_key/authorization/cookie/credential/session）；工具命令与 stdout/stderr 在 `JdbcOperationRunRecorder` 写库前脱敏、`OperationRunQueryService` 读回时兜底（覆盖历史明文行）；`OperationToolService` 返回结果与错误同口径；爬取正文/标题入库前脱敏、URL 去 query、`last_error` 只落错误码（不落异常原文/内部主机）；`InspectorEventService` 对 target/claim/reason/recommendation/evidence/metadata JSON 落库前脱敏 | 历史库中已存在的明文输出/证据未做一次性清洗（需备份后按时间窗清理）；日志框架级脱敏（nginx access log、Logback 消息体）未改动；TM-30/31 仅为单测，HTTP/真实爬取未运行 |
| SEC-12 | 已修（代码级） | Knowledge 默认 fail-closed：未配置 `KNOWLEDGE_API_KEY` 且未显式 `KNOWLEDGE_ALLOW_ANONYMOUS=true` 时启动即失败，请求层 503；匿名仅允许回环来源（`127.0.0.1`/`::1`，应用层判断，与绑定地址无关），非回环 403；摄入接口永不匿名（`ALLOW_INGEST=1` 不再放行，必须携带有效 `X-API-Key`）；`/api/health` 增加 `auth_mode`（`api_key`/`anonymous_loopback_only`/`misconfigured_fail_closed`） | 未启动真实 uvicorn 观测启动失败与 503（仅 TestClient 单测）；ai-service 未配 `KNOWLEDGE_API_KEY` 时 RAG 检索将 503（需在部署注入）；外网绑定/网络层隔离仍未做 |
| SEC-13 | 已修（代码级） | `SecurityAssertions.verifyDeploymentSecrets`：生产下数据源/Redis 密码为空或命中已知默认口令（`change-me-*`/root/password/123456/admin）、`SMARTOPS_API_KEY_ENCRYPTION_KEY` 为空 → `SECURITY_ASSERTION_FAILED` 拒绝启动；`docker-compose.yml` 移除 `change-me` 默认值，`MYSQL_ROOT_PASSWORD`/`MYSQL_PASSWORD`/`REDIS_PASSWORD` 改为 `${VAR:?}` 必填，取消 3306/6379 端口发布（仅容器网络可达）；Redis 以 `--requirepass` 启动；`application-prod.yml` 数据源口令改环境变量注入；`.env.example` 补齐必填项说明 | 未执行 `docker compose config/up`（docker 未运行；仅 YAML 解析通过），端口未发布/requirepass 生效为静态确认；`application-local.yml` 固定 AES key 仍保留（仅本地 profile，生产走断言拒绝空 key）；历史 `.env` 中的默认口令需人工替换 |

以上为单元/集成测试结论（SEC-15 断言 7 pass；SEC-03 `MultiExecServiceTest` 6 pass；SEC-11 定向 5 个测试类通过、后端全量 733 项 0 失败 0 错误（1 skipped）；SEC-12 `tests/knowledge` 106 pass；SEC-13 断言单测 `SecurityAssertionsTest` 见 §9（并行改动期间 pom 暂时不可构建时为 `NOT_RUN`）；SEC-04/05/09/10 见 `remediation-order.md` §9）。所有结论均来自本地 H2/单测与 TestClient，未启动 Java/ai-service/MySQL/Redis/nginx/uvicorn/docker；TM-01/02/03/10/11/18-24 的 HTTP/网络级复核仍为 `NOT_RUN`。

---

## 2. 风险详情

### SEC-01（P0，CWE-306/CWE-639）F03 聊天主链路未经 Java 认证

- **影响**：任何能访问 8001 或 nginx `/ai-api` 的调用方，无需 cookie/token 即可调用 LLM+RAG 聊天与 SSE；可耗尽模型额度、注入 Prompt、读取知识库召回内容；日志只含客户端自报 ID，无法追责与封禁。
- **证据**：
  - `ai-service/app/api/chat.py:42-61`（`POST /api/chat` 仅 `Depends(get_chat_service)`，无认证依赖）；`64-99`（`/api/chat/stream` 同样无认证）。
  - `ai-service/app/schemas/chat.py` 全文无 user/tenant 字段（检索确认无匹配）。
  - `deploy/nginx/nginx.conf:199-212`（`/ai-api/` 直接反代 `ai-service:8001`，未加 `auth_request` 或 IP 限制）。
  - `frontend/src/api/stream.ts:8,93-99`（`AI_SERVICE_BASE` 默认 `/ai`，浏览器 `fetch('/ai/api/chat/stream')`，不带 `credentials`，仅带 `X-Request-ID`/`X-Task-ID`；生产可 `VITE_AI_SERVICE_URL=/ai-api`）。
- **复现输入（本地 fixture，不触外网）**：`POST http://127.0.0.1:8001/api/chat`，body `{"message":"hello"}`，无 Cookie、无 Authorization，伪造 `X-Run-ID: attacker-1`。
- **预期拒绝**：401/403（无主体即拒绝）；SSE 入口同样拒绝，并记录拒绝原因与来源 IP。
- **回滚/缓解**：短期在 nginx 关闭 `/ai-api` 公网映射，仅保留同源 `/api`；中期由 Java 签发短时 run token（绑定 user/run/exp）供 ai-service 校验。回滚只需恢复 nginx 配置，不改业务代码。
- **归属任务**：N06 + HC-01；本任务只提供审计与测试矩阵。

### SEC-02（P0，CWE-345/CWE-639）F03 run_id/主体不一致

- **影响**：`run_id` 完全由请求头决定，服务端不生成、不校验归属；两个调用方可复用同一 `run_id`，导致 SSE 事件、审计日志、前端任务追踪互相覆盖或伪造"某 run 已执行/已失败"。metadata 可覆盖 request/task，但不能覆盖 run_id（已核实）。
- **证据**：
  - `ai-service/app/core/correlation.py:36-46`（request/task 从 metadata 或 header 取值；`run_id` 只从 `X-Run-ID` 取，缺失时 uuid）。
  - `ai-service/app/api/chat.py:23-39`（读取请求头并 `resolve_ids`）。
  - `ai-service/app/services/chat.py:63-66`（run_id 写入日志上下文；审计时快照）。
  - `agent/runtime_events.py:21-26`（事件按 run_id 归属）。
  - `frontend/src/api/stream.ts:96-99`（客户端可自带 `X-Run-ID`）。
- **复现输入**：本地同时发起两个请求，均带 `X-Run-ID: run-A`、不同 message；再发第三个 `X-Run-ID: run-victim`。
- **预期拒绝**：同一 run_id 不同主体/不同 payload 应 409；未签名 run_id 应 401；run_id 服务端生成并回传。
- **回滚/缓解**：接入认证前，先校验 run_id 必须由内部签名/HMAC 携带 subject，否则拒绝；客户端值降级为 `client_request_id`，不得作为 run 身份。
- **归属任务**：N06 + HC-01。

### SEC-03（P0，CWE-345/CWE-367）MultiExec "双人确认"可自批且可并发重放

- **影响**：`requiredApprovals=2`（CRITICAL 或生产多目标，`OperationRiskPolicy.java:25-26`）表面双人复核，实际第二确认值就是第一次返回给同一调用方的 nonce；任何登录用户可自批 `rm -rf` 等 CRITICAL 命令；预览保存在内存 Map 无 TTL/上限；`execute` 为"读-删-执行"非原子，同一 preview 并发可双执行。
- **证据**：
  - `MultiExecService.java:26-37`（preview 返回 `confirmationNonce` 给调用方）。
  - `MultiExecService.java:39-45`（`secondConfirmationNonce` 与 `confirmationNonce` 相等即放行，未校验第二人身份）。
  - `MultiExecService.java:46-55`（执行前 `remove`，无锁，并发可都通过）。
  - `MultiExecService.java:24`（`previews` 进程内 Map）。
  - `MultiExecController.java:19-31`（任何已认证用户可 preview/execute；路径 `/api/operations/multi-exec`）。
- **复现输入（本地 HTTP fixture）**：登录用户对自有 runtime 调 `POST /api/operations/multi-exec/preview`，取响应 `confirmationNonce`，再调 `POST /api/operations/multi-exec/execute`，body 中 `confirmationNonce` 与 `secondConfirmationNonce` 同值。
- **预期拒绝**：第二确认必须来自**不同主体**且由服务端签发一次性凭据；同一主体自批 409（现有码 `SECOND_CONFIRMATION_REQUIRED`，整改建议 `SECOND_APPROVER_REQUIRED`）；重复 previewId 仅一次 200。
- **回滚/缓解**：保留 API 形状，内部改为"preview 记录 + 第二审批人签名 + 数据库条件消费"；未完成前可将 `requiredApprovals>=2` 直接拒绝执行（fail-closed）。
- **归属任务**：HC-02 提整改单；审批语义与 HC-01 对齐。

### SEC-04（P1，CWE-294/CWE-384）Agent 审批未绑定 run_id，legacy 审批无指纹/过期

- **影响**：1) fingerprint 含 request_id/user/environment/step/tool/action/arguments，**不含 run_id**，同一用户复用 request_id 与参数可跨 run 重放；2) `create_request`（legacy）审批 `execution_fingerprint=None` 且无 `expires_at`，`validate` 永远 False，但 `approve` 仍可置 APPROVED，若调用方只查 status 或走 `SafeAgent.approval_granted` 布尔通道则形同虚设；3) 审批仅存进程内 `_records`，重启即丢，无持久化审计；`approve` 不校验审批人≠申请人。
- **证据**：
  - `agent/safety/approval.py:73-91`（指纹字段，无 run_id；TTL 300s）。
  - `agent/safety/approval.py:93-113`（validate + consume 一次性）。
  - `agent/safety/approval.py:115-137`（legacy `create_request` 无指纹、无过期）。
  - `agent/safety/approval.py:155-168`（`_review` 仅校验 reviewer 非空，不校验身份/与申请人关系）。
  - `agent/safety/approval.py:29-40`（`_records` 内存字典）。
  - `agent/safety/safe_agent.py:24-32`（布尔 `approval_granted` 旁路通道）。
- **复现输入**：本地单测：run A 下 `create_for_step(request_id="r-1", user_id=1, step_id="s-1", tool="exec", action="run", arguments={"cmd":"x"})` → approve → run B 用相同字段 `validate(...)`；另构造 legacy `create_request` + `approve` 后 `validate`。
- **预期拒绝**：run_id 不同则 `False` + `APPROVAL_CONTEXT_MISMATCH`；legacy 审批不得进入可用态；审批审计落库（approval_id/run_id/approver/expires/fingerprint）。
- **回滚/缓解**：`ApprovalContext` 增 `run_id` 并纳入 fingerprint（同步改 `SafeAgent`/`PolicyEngine` 调用方），保留一次性 consume。
- **归属任务**：HC-02 + HC-07。

### SEC-05（P1，CWE-345/CWE-613）Java TeamAgentRun grant 的绑定与一次性语义不完整

- **影响**：已有正确方向（服务端算 digest、审批人不得自批、条件 UPDATE 原子消费），但：
  1. `grant_token` 生成落库后**从未校验**（消费时直接置 NULL），"签名 grant"名义存在、实际不参与鉴权；持有 runId + 同用户 session 即可执行。
  2. digest 基于渲染后的命令文本，而非规范化 `parameters_json` + 工具版本；渲染逻辑变化时无法证明"审批的就是将要执行的"。
  3. 无审批取消/撤回状态、无创建幂等键；重复请求会产生多条待审 run。
  4. 审计只记 runId/actor/basis（`166-167`），不记 digest，事后无法证明绑定。
  5. 审批人比较用 `Long` 引用比较 `run.previewedBy() != actor.id()`（`156`），user id >127 时可能总被判"非预览人"而 409（fail-closed 可用性缺陷，不是越权）。
- **证据**：
  - `TeamAgentRunService.java:120-126`（preview 计算 digest）。
  - `TeamAgentRunService.java:148-168`（approve、自批禁止、300s 过期、写 basis）。
  - `TeamAgentRunService.java:160-164`（token/expiry 生成）。
  - `TeamAgentRunService.java:184-206`（consumeGrant：195-197 digest 比较，198-200 过期，201-203 原子 UPDATE 并置空 token；无 token 校验）。
  - `TeamAgentRunController.java:71-83`（preview 服务端生成 digest）；`85-112`（execute 重新计算 digest）。
- **复现输入**：对已 approve 的 run：a) 不带 `grantToken` 调 execute；b) 连续两次 execute；c) fixture 直接改 `parameters_json` 后 execute。当前 a 成功、b 第二次 409 `TEAM_RUN_GRANT_USED`、c 409 `TEAM_RUN_PREVIEW_CHANGED`。
- **预期拒绝**：a 409 `GRANT_TOKEN_REQUIRED`；b 仅一次 200；c 409 `TEAM_RUN_PREVIEW_CHANGED`；审计必须存 digest 与 approver。
- **回滚/缓解**：启用 token 校验若与旧前端不兼容，可先服务端强制 `requireToken`，保留一次性消费；不得回退为只凭 runId。
- **归属任务**：HC-02 提整改单；HC-01 定义审批记录字段。

### SEC-06（P0，CWE-918）F06 爬取 SSRF

- **影响**：`publicTarget` 只检查 URL 主机字符串，不做 DNS 解析、不做连接期 IP 固定。可绕过：
  - `http://localhost.:8080/`（尾点；`uri.getHost()` 常返回 `localhost.`，`equals/endsWith(".localhost")` 均 false）。
  - `http://[::ffff:127.0.0.1]:8080/`（IPv4-mapped IPv6，去括号后不匹配 `::1`/`127.*`）。
  - IPv6 未覆盖：`fe80::/10`、`fc00::/7`、`::`、`2001:db8::`。
  - 未覆盖私有段：`100.64.0.0/10`（CGNAT）、`198.18.0.0/15`、`0.0.0.1`。
  - DNS rebinding：校验时公网，连接时内网（未 pin 解析地址）。
  - **首跳不复检**：`run()` 直接把 DB `seedUrl` 入队，`fetch()` 只对重定向 Location 复检；迁移前/被篡改 seed 可直连内网。
  - 重定向最多 4 跳且逐跳检查，但仍是字符串检查，配合 DNS 可绕过。
- **其他边界缺陷**：
  - `BodyHandlers.ofString()` 一次读全响应，**下载侧无 Content-Length/字节上限**；`MAX_CONTENT=20_000`（`38`）只截断入库，不能阻止 200MB/OOM。
  - `maxPages<=50`（`69-70`），无全局/单用户并发限制，仅每页 `sleep(300ms)`（`130-137`）。
  - 单请求超时 8s 仅限制单跳（`179-181`），50 页 × 多跳可长时间占用线程。
  - `HttpClient` 未显式设置 `ProxySelector`（`53-56`），是否走 JVM/环境代理 UNKNOWN；若走代理可绕过 IP 策略。
- **证据**：
  - `KnowledgeCrawlService.java:291-300`（`publicTarget` 字符串判断）。
  - `KnowledgeCrawlService.java:275-289`（创建时唯一一次校验）。
  - `KnowledgeCrawlService.java:92-107`（`run()` 直接把 DB `seedUrl` 入队并 fetch，首跳未调用 `publicTarget`）；`170-199`（fetch 只对重定向目标复检）。
  - `KnowledgeCrawlService.java:185`（无上限下载）；`38`（仅入库截断）。
  - `KnowledgeCrawlService.java:53-56`（HttpClient 未禁代理，connectTimeout 8s、NEVER 重定向）。
  - `KnowledgeCrawlService.java:188-195`（重定向循环、逐跳检查）。
  - `KnowledgeCrawlService.java:69-70`（maxPages 上限 50）；`130-137`（300ms 间隔）。
  - `KnowledgeCrawlService.java:117-121`（链接仅同 seedHost，正向保护）。
- **复现输入（全部指向本地 mock，禁止真实外网）**：`http://localhost.:18080/`、`http://[::ffff:127.0.0.1]:18080/`、`http://100.64.0.1:18080/`；mock 302 → `127.0.0.1:18080`；mock 1 字节/秒吐 60 秒；mock 返回 200MB body。
- **预期拒绝**：创建与每跳 fetch 均 400 `CRAWL_URL_BLOCKED`（记录解析 IP 与命中规则）；超限 413/截断；慢速总超时中止；单用户并发 429。
- **回滚/缓解**：短期先关闭爬取（`KNOWLEDGE_CRAWL_ENABLED=false`）并禁用历史 seed；不得只扩大黑名单。
- **归属任务**：HC-02 → 后续 IMPLEMENT；HC-04 配合。

### SEC-07（P0，CWE-269/CWE-863）管理权限在缺 profile/DB 异常时沿用历史 admin/ROOT 兼容语义

- **影响**：
  1. `hasPlatformCapability` 在 `platform_admin_profile` 缺行时直接返回 `true`（全部能力）——任何被提升为 admin 但未写 profile 的账号等价 ROOT。
  2. `createAccount` 只写 `app_user`，不写 profile；`updateRole` 提升 admin 同样不写 → **新管理员天然全能力**，不受能力列表约束。
  3. `platformLevel` 在缺 profile 时返回 `"ROOT"`；`platformAdministrators` 查询异常时把全部 admin 当 `root` 返回（fail-open 展示）。
  4. 真正 DB 异常时 `profileOf` 抛 500（fail-closed，正确），但"缺行即全能力"是逻辑 fail-open，与 DB 异常无关。
- **证据**：
  - `UserAccountService.java:120-128`（122-124：`profiles.isEmpty()` → `return true`；127：能力查询）。
  - `UserAccountService.java:217-221`（220：无 profile → `ROOT`）。
  - `UserAccountService.java:249-262`（`createAccount` 无 profile INSERT）。
  - `UserAccountService.java:264-276`（提升 admin 仅改 `app_user.role` 并 bumpVersion，无 profile）。
  - `UserAccountService.java:154-155`（治理查询异常回退所有 admin 为 `root`）。
  - `PlatformAdminGovernance.java:12-14`（ROOT = 全部能力）。
- **复现输入（本地 H2/测试替身）**：a) admin 会话调用能力门禁接口；b) mock `JdbcTemplate` 抛 `DataAccessException` 调 `hasPlatformCapability`；c) 新建 admin 后查 `platform_admin_profile` 为空。
- **预期拒绝**：缺 profile 的普通 admin 只有最小只读能力（403 其他）；治理表故障 500/503 且不授予提升；被提升账号必须显式写 profile（默认空能力）。
- **回滚/缓解**：担心阻断历史管理员时，用迁移期**显式 allowlist**（按 user_id 一次性授予），而非"缺行即全能力"；必须可回退为只读。
- **归属任务**：HC-02 P0；与 HC-01/DB owner 协同。

### SEC-08（P1，CWE-639/CWE-284）Server/Inspector 查询无统一 scope，Loop 全局事件投影

- **影响**：1) 任意登录用户可列举全部服务器/指标，泄露主机名、IP、负载；2) `GET /api/inspector/events` 返回全局事件（表无 owner），可读他人巡检结果/建议/evidence；3) `GET /api/agent/loops` 把全局事件同步进当前用户闭环（`source_ref` 去重），造成跨用户投影 + 重复学习（SEC-10）；4) `X-User-Id` 多处 controller 直接读取（default 1），当前靠 `TrustedUserIdFilter` 兜底，scope 未统一到 principal。
- **证据**：
  - `ServerController.java:36-47`（GET 列表/详情无 scope）。
  - `ServerMetricController.java:30-46`（指标无 scope）。
  - `InspectorController.java:22-35`（事件查询无 principal 校验）。
  - `InspectorEventService.java:28-47`（直接查全表）。
  - `V20261002__operations_and_accounts.sql:3`（`inspector_event` 无 user/team 列）。
  - `DecisionLoopService.java:171-180`（全量读取 + 按 source_ref 去重写入当前用户）。
  - `DecisionLoopController.java:18-23`（`X-User-Id` 默认 1）。
- **复现输入**：用户 A 无服务器；用户 B 造 1 台 server/1 条 inspector 事件后，A 调 `/api/servers`、`/api/servers/{B}/metrics`、`/api/inspector/events`、`/api/agent/loops`。
- **预期拒绝**：无 team/owner 绑定返回空或 403；闭环只消费与 A 关联的事件；`X-User-Id` 仅在受控内部路径可用。
- **回滚/缓解**：先加读侧 team 过滤（不改数据），再补 `inspector_event` 归属列；迁移期全局视图仅审计管理员可用并留审计。
- **归属任务**：HC-01（数据模型）+ HC-02（scope 规则）。

### SEC-09（P1，CWE-362）`MAX(id)` 取刚插入 ID 的同 owner 并发歧义

- **影响**：创建库/条目/记忆/source 后 `MAX(id)` 反查刚插入行；同 user 并发时可能取到更高 id 的他人（同用户）记录，返回错误内容或后续写错对象。**不跨用户越权**（SQL 带 `user_id`），但破坏创建契约与审计一致性。
- **证据**：
  - `PersonalKnowledgeService.java:40`（`MAX(id) WHERE user_id` 取库）。
  - `PersonalKnowledgeService.java:104`（`MAX(id) WHERE user_id AND library_id` 取条目）。
  - `OperatorMemoryService.java:22`、`49`（记忆 id 反查）。
  - `KnowledgeCrawlService.java:73`（source id 反查）。
  - 正确模式对照：`TeamAgentRunService.java:75-86`、`JdbcOperationRunRecorder.java:23-39` 使用 `GeneratedKeyHolder`。
- **复现输入**：同用户两线程/两请求并发创建两条知识条目，用唯一标题校验 A 返回 id 是否等于 A 自己的插入 id。
- **预期拒绝**：创建必须返回本次插入主键（`GeneratedKeyHolder`/`RETURNING`）或业务唯一键回查；并发不得返回他人记录。
- **回滚/缓解**：只改创建返回路径，不改表结构。
- **归属任务**：HC-01。

### SEC-10（P1，CWE-837/CWE-362）重复 review/GET 同步导致重复 learn 与 memory feedback

- **影响**：1) 每次 `POST /api/agent/loops/{id}/review` 无条件 `learn()` → 重复 review 重复创建 learned memory、累加 `learned_count`、抬高/拉低 confidence；2) `syncFromInspector` 用 `NOT EXISTS source_ref` 去重，但表**无唯一索引**，并发 GET 可同时插入重复 loop；3) 全局事件投影让每个用户首次 GET 都复制一份全局事件，放大重复。
- **证据**：
  - `DecisionLoopService.java:141-153`（review 后直接 learn，无幂等）。
  - `DecisionLoopService.java:171-180`（`NOT EXISTS` + INSERT，无唯一约束）。
  - `DecisionLoopService.java:204-211`（sync 后逐条 learn）。
  - `DecisionLoopService.java:216-249`（learn 每次新建记忆；234-240 插入 learned memory）。
  - `V20261024__agent_decision_loop.sql:27-28`（仅普通索引，无 `(user_id, source_type, source_ref)` 唯一键）。
- **复现输入**：同一 loop 连续 5 次 review；两个并发 GET `/api/agent/loops`（前置 1 条全局 inspector 事件）；断言 learned_count、memory 行数、loop 行数。
- **预期拒绝**：同一 loop 同 stage 的 review 幂等（第二次 `learned=false` 或 409）；同步以唯一键 upsert；learn 以 `(user, source_ref, lesson_hash)` 去重。
- **回滚/缓解**：先应用层幂等，再加唯一索引（需评估历史重复数据清理）。
- **归属任务**：HC-01/HC-07。

### SEC-11（P1，CWE-532/CWE-312）日志/Prompt/凭据泄漏面

- **影响**：1) `OperationToolService` 把原始 stdout/stderr/command 交给 recorder 落库，API 可读回；`OperationRedactor` 仅在 SSH/WS 路径使用且只覆盖 `key=value` 简单形态，无法覆盖 Bearer、JSON、base64、多行 env；执行 `env`/`cat .env`/`docker inspect` 即把凭据明文写入数据库与前端。2) 爬取失败原因 `last_error` 落库并回显（含内部主机/异常细节）；正文以 Markdown 明文入库（可能含个人信息/密钥）。3) 巡检 evidence 原样落库。4) 管理二次确认口令走 `X-Admin-Password` 请求头；nginx access 日志记录完整 request line（含 query）。5) 聊天日志只记 ID（审计时快照 `ai-service/app/services/chat.py:63-66`、`242-245`），属正向保护；但 tool_calls/inspector evidence 会带输出，需单独约束。
- **证据**：
  - `JdbcOperationRunRecorder.java:45-50`（stdout/stderr/command 原样 INSERT）。
  - `V20261002__operations_and_accounts.sql:14`（`operation_command` 预留 `output_redacted`，但当前执行/记录路径未用该链路）。
  - `OperationToolService.java:189-192`（执行结果直接 `recordCommand`，未 redactor）。
  - `OperationRedactor.java:6-14`（仅窄正则 `key=value`）。
  - `SshConnectionAdapter.java:203-207`（仅 SSH 路径调用脱敏）。
  - `OperationRunQueryService.java:54-57`（原样读回 stdout/stderr）。
  - `KnowledgeCrawlService.java:128`、`140-141`（错误落库）；`165-166`（正文入库）。
  - `InspectorEventService.java:114-119`（evidence 原样落库）。
  - `deploy/nginx/nginx.conf:68-79`（access log 含 request）。
  - `AdminConfirmationFilter.java:28`（口令走请求头）。
- **复现输入**：本地工具输出 `API_TOKEN=abc123`/`Authorization: Bearer xyz`；爬取 mock 页面含 `email=...`；调 run 详情接口并查库。
- **预期拒绝**：落库/回显前统一脱敏为 `[REDACTED]`（覆盖 password/token/secret/api_key/authorization/cookie/private_key 与 Bearer/JSON 形态）；正文只存正文不存 Cookie/Header；日志不记录请求头与正文。
- **回滚/缓解**：先加"写库前统一 redactor"，再做历史数据清洗；原始输出仅本地调试开关且默认关。
- **归属任务**：HC-02 + HC-05 + HC-07。

### SEC-12（P1，CWE-306）Knowledge `/api/search` 默认开放

- **影响**：`KNOWLEDGE_API_KEY` 未配置时 `require_api_key` 直接放行；知识服务默认监听 0.0.0.0:8002。匿名可检索全部私有知识库；若 `ALLOW_INGEST=1`，匿名可写入/污染知识库，影响 RAG 与后续决策。
- **证据**：
  - `knowledge/server.py:95-109`（未配置 key 不校验；配置后常量时间比较）。
  - `knowledge/server.py:112-115`（`/api/search` 依赖）。
  - `knowledge/server.py:118-126`（ingest 仅在 key 或 `ALLOW_INGEST` 下放行）。
  - `knowledge/server.py:22`（`ALLOW_INGEST` 环境开关）；`258`（health 暴露 `auth_required`）。
  - `ai-service/app/services/rag.py:61-62`（仅配置 key 才带 `X-API-Key`；审计时快照）。
- **复现输入**：不设置 `KNOWLEDGE_API_KEY`（本次不启动，仅本地测试用例描述），`POST http://127.0.0.1:8002/api/search {"query":"..."}` 不带 key；另设 `ALLOW_INGEST=1` 调 `/api/documents`。
- **预期拒绝**：未配置 key 拒绝启动，或要求显式 `KNOWLEDGE_ALLOW_ANONYMOUS=true` 且仅绑 127.0.0.1；ingest 永不允许匿名。
- **回滚/缓解**：优先部署设 key + 内网绑定；代码改"未配置即 fail-closed"需与 HC-04 协同。
- **归属任务**：HC-04 / HC-02。

### SEC-13（P1，CWE-798/CWE-1188）部署默认凭据与端口发布

- **影响**：默认/示例口令可直接登录或连接；数据库、Redis 端口发布到宿主；本地固定加密密钥；生产未强制覆盖则整体失守。
- **证据**：
  - `backend/src/main/resources/application-prod.yml:7-9`（`MYSQL_USERNAME:root`，`MYSQL_PASSWORD:` 空默认）。
  - `deploy/docker/docker-compose.yml:44`、`50`（`change-me-root-password`）。
  - `deploy/docker/docker-compose.yml:55-58`（3306 端口发布）；`111-113`（6379 端口发布）。
  - `deploy/docker/redis/conf/redis.conf:9`（`bind 0.0.0.0`；全文件检索未发现 `requirepass`）。
  - `backend/src/main/resources/application-local.yml:61`（固定本地 AES key）。
  - `backend/src/main/resources/application.yml:67-69`（bootstrap 管理员口令可空，需显式环境变量）。
- **复现输入**：静态配置核对；未来 RUN 可本地起 compose 后 `redis-cli -h 127.0.0.1 ping`（本次不执行）。
- **预期拒绝**：启动预检发现默认口令/发布端口即失败；Redis 必设 `requirepass` 且不发布宿主；prod 必须 secret 注入。
- **回滚/缓解**：只改部署与环境变量，无代码回滚需求。
- **归属任务**：HC-05；HC-02 只登记。

### SEC-14（P2，CWE-918）模型连接 baseUrl 内网 SSRF

- **影响**：任意已认证用户可创建 `baseUrl` 指向任意 http(s) 地址的模型连接（无私有地址校验）；调用 `/runtime|invoke` 受内部 token 保护，浏览器直接利用可能性低，但一旦内部 agent 使用该连接，会把请求发往内网/元数据地址并可能回显响应。
- **证据**：
  - `ModelConnectionService.java:322-339`（仅 trim/去尾斜杠，无 host 校验）。
  - `ModelProviderClient.java:85-96`（按 `URI.create(baseUrl + path).toURL()` 发请求，任意 host）。
  - `ModelConnectionController.java:40-58`（创建/更新仅需登录，无管理员限制）。
  - `SecurityConfig.java:31`、`54`（`/runtime|invoke` 在内部 token 路径）。
  - `InternalTokenAuthenticationFilter.java:33-43`（内部 token 覆盖路径）。
- **复现输入**：登录用户创建 baseUrl=`http://127.0.0.1:18080/v1`，随后 fixture 直接带内部 token 调 `/api/model-connections/{id}/runtime`。
- **预期拒绝**：创建/更新时拒绝私有/回环/非 http(s) 地址（与爬取共用 IP 校验）；或仅管理员可创建。
- **回滚/缓解**：服务层加 host 校验，不改表；已存在的恶意连接需清理任务。
- **归属任务**：HC-02；与 SEC-06 共用校验工具。

### SEC-15（P2，CWE-639/CWE-807）内部 token 覆盖面窄 + `X-User-Id` 遗留头 + bypass 开关

- **影响**：内部 token 仅覆盖 5 条路径，其余内部语义端点若误配为 permitAll 就退化为"无认证 + 信任客户端头"；`smartops.security.internal-bypass` 开启后直接放行内部路径（默认 false，但可由 `SMARTOPS_INTERNAL_BYPASS` 打开）。当前 `TrustedUserIdFilter` 覆盖 `SessionUser` 头值，普通 session 请求不可直接越权；但 `defaultValue="1"` 使"principal 非 SessionUser 且未拒绝"时默认落到 user 1。
- **证据**：
  - `TrustedUserIdFilter.java:18-28`（仅覆盖，不拒绝头）。
  - `InternalTokenAuthenticationFilter.java:33-43`（路径枚举）；`21-30,51-53`（`developmentBypass` 跳过校验）；`application.yml:129`（默认 false，可由 `SMARTOPS_INTERNAL_BYPASS` 覆盖）。
  - `SecurityConfig.java:52-62`（anyRequest 与 permitAll 清单）。
  - `DecisionLoopController.java:20`、`OperationRunController.java:23`（`X-User-Id` 默认 1）。
- **复现输入**：已登录 A 带 `X-User-Id: 999` 调列表/创建接口，断言落库 `user_id == A`；匿名同头断言 401；另设 `SMARTOPS_INTERNAL_BYPASS=true` 调 `/api/inspector/check` 断言应启动失败或拒绝。
- **预期拒绝**：不读取客户端用户头（一律 principal）；内部调用使用独立 token + 显式 `onBehalfOf` 并审计；生产断言 bypass=false。
- **回滚/缓解**：分批替换 controller 取用户方式，保留 filter 兜底，不回退。
- **归属任务**：HC-01/HC-02。

---

## 3. 与交接书/基线的一致性

- F03（聊天无 Java 认证）、F06（爬取 SSRF）、审批绑定缺口均在交接书 F 列表；新增可精确派单的子缺陷：SEC-03（MultiExec 同一 nonce 自批）、SEC-07（无 profile 即全能力）、SEC-09（`MAX(id)`）、SEC-14（模型连接 SSRF）。
- 与 `route-map.md` 一致：`/ai-api` 为 ai-service 直连、`/api` 走 Java session、Knowledge 仅在配置 key 时校验。
- 与 `status-baseline.md` 一致：未启动服务、未跑测试；所有"当前行为"为静态推导，实际运行在 RUN 阶段验证。
- 本文不含已利用结论；SEC-06 绕过形式为代码级推导，标注"未做故障注入"。
