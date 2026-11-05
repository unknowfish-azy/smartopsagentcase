# HC-02 安全与权限审计 — 风险矩阵（静态只读基线）

- 审计日期：2026-11-05
- 审计方式：仅静态阅读代码与配置；**未启动服务、未做故障注入、未连接真实数据库、未对任何真实第三方发起探测**。下列风险均为"可由代码推导的缺陷假设"，不等同于已在运行环境利用成功。
- 基线复用：`docs/audit/20261105/route-map.md`、`docs/audit/20261105/status-baseline.md`；本文件与二者不矛盾，只补充安全视角。
- 优先级定义：P0 = 可导致认证缺失、审批绕过、命令执行或全量管理员权限；P1 = 跨主体读取、审批/审计语义不完整、敏感数据落库；P2 = 纵深防御与配置硬化。
- 状态标注：`静态确认` 表示代码路径已核实；`UNKNOWN` 表示依赖部署配置或运行时行为，未验证；`BLOCKED` 表示缺少本地可复现 fixture，无法在本次审计中验证。
- 归属任务代号沿用交接书：HC-01（核心决策/数据模型）、HC-02（本任务）、N06（聊天主链路）、HC-04（知识）、HC-05（部署）、HC-07（闭环/记忆）。

## 0. 必须保留的现有保护（不得在整改中删除或弱化）

1. `TrustedUserIdFilter`：`backend/src/main/java/com/smartops/security/TrustedUserIdFilter.java:18-28` 在已认证且 principal 为 `SessionUser` 时，用 session 用户覆盖 `X-User-Id` 请求头，防止客户端直接指定主体。
2. 内部 token 过滤：`InternalTokenAuthenticationFilter.java:33-43` 仅对 `/api/model-connections/*/runtime|invoke` 与 `/api/inspector/check|beat` 生效；`InternalTokenAuthenticationFilter.java:45-53` 未配置 token 时返回 503（fail-closed），请求头缺失/错误返回 401，且不授予 session 权限。
3. `AdminConfirmationFilter.java:23-56`：管理端写操作需 `X-Admin-Password` 二次确认，且与 `X-CSRF-Token` 校验；不通过则 403。
4. `TeamAgentRunService.java:195-203` 的 grant 消费为条件 UPDATE（`status='APPROVED'` → `EXECUTED`），`changed != 1` 返回 409，保证一次性消费的数据库原子性；审批前强制 `markPreview` 且 `previewed_by` 必须等于审批人（`TeamAgentRunService.java:148-168`），禁止预览人自批。
5. Agent `ApprovalManager` 已有执行指纹（request/user/environment/step/tool/action/arguments）与一次性消费：`agent/safety/approval.py:73-91`、`93-113`；`PolicyEngine._approval_reason` 在非只读工具上强制校验：`agent/policies/policy_engine.py:69-76`。
6. `SecurityConfig.java:52-62` 默认 `anyRequest().authenticated()`，仅聊天健康检查、匿名会话令牌、内部 token 路径、OpenAI 兼容网关为 `permitAll`；网关自身仍校验 Bearer key（`ModelGatewayController.java:167-193`），不是裸奔入口。
7. 终端 WebSocket：`AuthenticatedSessionHandshakeInterceptor.java:20-33` 校验 session，`OperationsTerminalWebSocketHandler.java:52-66` 再次校验当前用户，Origin 仅允许 localhost（`OperationsWebSocketConfig.java:22-30`，生产环境域名收窄为 UNKNOWN）。
8. `KnowledgeCrawlService.java:188-195` 已明确禁用自动重定向并手写最多 4 跳、逐跳调用 `publicTarget`；这是 SSRF 整改的既有基线，不应退化为"无任何防护"。

## 1. 风险总表

| ID | 优先级 | CWE | 简述 | 归属 |
| --- | --- | --- | --- | --- |
| SEC-01 | P0 | CWE-306 / CWE-639 | ai-service 聊天主链路无身份校验，经 nginx `/ai-api` 对公网可达 | N06 / HC-01 |
| SEC-02 | P0 | CWE-345 / CWE-639 | `X-Run-ID` 客户端任意指定，与主体/Java run 无绑定，可串号与伪造事件归属 | N06 / HC-01 |
| SEC-03 | P0 | CWE-345 / CWE-367 | MultiExec "双人确认"使用同一个 nonce，等于自批；并发可重复执行 | HC-02 / HC-01 |
| SEC-04 | P1 | CWE-294 / CWE-384 | Agent 审批未绑定 run_id，同一 request_id+参数可跨 run 复用；legacy 审批无指纹/无过期 | HC-02 / HC-07 |
| SEC-05 | P1 | CWE-345 / CWE-613 | Java run grant 的 digest 只绑渲染命令，grant_token 生成但从不校验，无取消与幂等键 | HC-02 / HC-01 |
| SEC-06 | P0 | CWE-918 | 爬取 SSRF：仅字符串黑名单，无 DNS/IP 解析、IPv6/映射地址与尾点绕过、首跳不复检、无响应体上限 | HC-02 |
| SEC-07 | P0 | CWE-269 / CWE-863 | 无 `platform_admin_profile` 的 admin 被视为全能力 ROOT；新建/提升 admin 不写 profile | HC-02 |
| SEC-08 | P1 | CWE-639 / CWE-284 | Server/Inspector 查询无统一 scope；全局 inspector 事件被投影进每个用户的决策闭环 | HC-01 / HC-02 |
| SEC-09 | P1 | CWE-362 | `MAX(id)` 取刚插入 ID，同 owner 并发下可能返回他人（同用户）记录 | HC-01 |
| SEC-10 | P1 | CWE-837 / CWE-362 | 重复 review/GET 同步重复 learn、重复 memory feedback，置信度与证据被放大 | HC-01 / HC-07 |
| SEC-11 | P1 | CWE-532 / CWE-312 | 工具 stdout/stderr、爬取正文与错误、管理口令请求头等敏感面落库/落日志且未统一脱敏 | HC-02 / HC-05 |
| SEC-12 | P1 | CWE-306 | Knowledge `/api/search` 仅在配置 KEY 时校验，默认开放；`ALLOW_INGEST=1` 时匿名可写 | HC-04 / HC-02 |
| SEC-13 | P1 | CWE-798 / CWE-1188 | 部署默认口令与端口发布（MySQL root/change-me、Redis 0.0.0.0:6379 无 requirepass、本地固定 AES key） | HC-05 |
| SEC-14 | P2 | CWE-918 | 模型连接 baseUrl 任意 http(s)，无内网地址限制（调用入口受内部 token 保护） | HC-02 |
| SEC-15 | P2 | CWE-639 / CWE-807 | 内部 token 仅覆盖 5 条路径；`X-User-Id` 仍被多处 controller 直接读取，未来新增 permitAll 路径即成 IDOR | HC-01 / HC-02 |

---

## 2. 风险详情

### SEC-01（P0，CWE-306/CWE-639）F03 聊天主链路未经 Java 认证

- **影响**：任何能访问 8001 或 nginx `/ai-api` 的调用方，无需任何 cookie/token 即可调用 LLM+RAG 聊天与 SSE；可耗尽模型额度、注入 Prompt、读取知识库召回内容；日志只含客户端自报 ID，无法追责与封禁。
- **证据**：
  - `ai-service/app/api/chat.py:42-61`（`POST /api/chat` 仅 `Depends(get_chat_service)`，无认证依赖）；`ai-service/app/api/chat.py:64-99`（`/api/chat/stream` 同样无认证）。
  - `ai-service/app/schemas/chat.py` 全文无 user/tenant 字段（已用检索确认，无匹配）。
  - `deploy/nginx/nginx.conf:199-212`（`/ai-api/` 直接反代 `ai-service:8001`，未加 `auth_request` 或 IP 限制）。
  - `frontend/src/api/stream.ts:93-99`（浏览器端 `fetch('/ai-api/chat/stream')`，不带 `credentials`，仅带 `X-Request-ID`/`X-Task-ID`）。
- **复现输入（本地 fixture，不触外网）**：`POST http://127.0.0.1:8001/api/chat`，body `{"message":"hello"}`，无 Cookie、无 Authorization，伪造 `X-Run-ID: attacker-1`。
- **预期拒绝**：整改后返回 401/403（无主体即拒绝）；SSE 入口同样拒绝，并记录拒绝原因与来源 IP。
- **回滚/缓解**：短期在 nginx 关闭 `/ai-api` 公网映射，仅保留同源 `/api` 代理；中期由 Java 签发短时 run token（绑定 user/run/exp）供 ai-service 校验。回滚点：恢复 nginx 配置即可，不改业务代码。
- **归属任务**：N06（聊天主链路）+ HC-01（主体模型）；本任务只提供审计与测试矩阵。

### SEC-02（P0，CWE-345/CWE-639）F03 run_id/主体不一致

- **影响**：`run_id` 完全由请求头决定，服务端不生成、不校验归属；两个调用方可复用同一 `run_id`，导致 SSE 事件、审计日志、前端任务追踪互相覆盖或伪造"某 run 已执行/已失败"。metadata 可覆盖 request/task，但**不能**覆盖 run_id（已核实），所以风险集中在 run_id 可任意指定。
- **证据**：
  - `ai-service/app/core/correlation.py:36-46`（request/task 从 header 或 metadata 取值；`run_id` 只从 `X-Run-ID` 取）。
  - `ai-service/app/api/chat.py:23-39`（读取请求头并调用 `resolve_ids`）。
  - `ai-service/app/services/chat.py:57-61`（run_id 直接写入 SSE 事件与日志上下文）。
  - `agent/runtime_events.py:21-26`（事件按 run_id 归属）。
  - `frontend/src/api/stream.ts:96-99`（客户端可自带 `X-Run-ID`）。
- **复现输入**：本地同时发起两个请求，均带 `X-Run-ID: run-A`、不同 message；再发起第三个请求 `X-Run-ID: run-victim`。
- **预期拒绝**：同一 run_id 不同主体/不同 payload 应 409；未由 Java 创建或未签名的 run_id 应 401；服务端生成 run_id 并回传。
- **回滚/缓解**：在接入认证前，先在 ai-service 校验"run_id 必须由内部签名/HMAC 携带 subject"，否则拒绝；保留客户端传入仅作 trace 关联时降级为 `client_request_id`，不得作为 run 身份。
- **归属任务**：N06 + HC-01。

### SEC-03（P0，CWE-345/CWE-367）MultiExec "双人确认"可自批且可并发重放

- **影响**：`requiredApprovals=2`（CRITICAL 或生产多目标，`OperationRiskPolicy.java:25-27`）表面上是双人复核，实际第二个确认值就是第一次返回给同一调用方的 nonce；任何登录用户可自批执行 `rm -rf` 等 CRITICAL 命令；预览保存在内存 Map 无 TTL、无上限；`execute` 为"读-删-执行"非原子，同一 preview 并发两次可双执行。
- **证据**：
  - `MultiExecService.java:26-37`（preview 返回 `confirmationNonce` 给调用方）。
  - `MultiExecService.java:42-45`（`secondConfirmationNonce` 与 `confirmationNonce` 相等即放行，未校验第二人身份）。
  - `MultiExecService.java:46-55`（执行前 `remove`，无锁，并发可都通过）。
  - `MultiExecService.java:24`（`previews` 进程内 Map）。
  - `MultiExecController.java:19-31`（任何已认证用户可 preview/execute）。
- **复现输入（本地单元/HTTP fixture）**：登录用户对自有 runtime 调 `POST /api/operations/multi/preview`，从响应取 `confirmationNonce`，再调 `POST /api/operations/multi/execute`，body 中 `confirmationNonce` 与 `secondConfirmationNonce` 均为该值。
- **预期拒绝**：第二个确认必须来自**不同主体**且由服务端签发一次性凭据；同一主体自批返回 409 `SECOND_APPROVER_REQUIRED`；重复 previewId 仅一次 200，其余 409。
- **回滚/缓解**：保留现有 preview/execute API 形状，内部改为"preview 记录 + 第二审批人签名 + 数据库条件消费"；未完成前可将 `requiredApprovals>=2` 直接拒绝执行（fail-closed）。
- **归属任务**：HC-02 提整改单；审批语义与 HC-01 的"审批轴"对齐。

### SEC-04（P1，CWE-294/CWE-384）Agent 审批未绑定 run_id，legacy 审批无指纹/过期

- **影响**：
  1. `execution_fingerprint` 含 request_id/user/environment/step/tool/action/arguments，**不含 run_id**；同一用户复用 request_id 与相同参数，可在新的 run 中通过旧审批（跨 run 重放）。
  2. `create_request`（legacy）创建的审批 `execution_fingerprint=None` 且无 `expires_at`，`validate` 永远返回 False；但 `approve` 仍可把状态置为 APPROVED。若未来有调用方只检查 `status` 或直接走 `SafeAgent.approval_granted` 布尔通道，则审批形同虚设。
  3. 审批记录仅存于进程内 `_records`，重启即丢，无持久化审计；审批人身份是宿主传入的字符串，`approve` 不校验审批人≠申请人。
- **证据**：
  - `agent/safety/approval.py:73-91`（指纹字段，无 run_id；TTL 300s）。
  - `agent/safety/approval.py:93-113`（validate + consume 一次性）。
  - `agent/safety/approval.py:115-137`（legacy `create_request` 无指纹、无过期）。
  - `agent/safety/approval.py:139-168`（approve 不校验审批人身份/与申请人关系）。
  - `agent/safety/approval.py:29-40`（`_records` 内存字典）。
  - `agent/safety/safe_agent.py:24-55`（布尔 `approval_granted` 旁路通道）。
- **复现输入**：本地单测用 `ApprovalManager` 构造：run A 下 `create_for_step(request_id="r-1", user_id=1, step_id="s-1", tool="exec", action="run", arguments={"cmd":"x"})` → approve → run B 用完全相同字段 `validate(...)`；再构造 legacy `create_request` + `approve` 后 `validate`。
- **预期拒绝**：context 中发现 run_id 不同则 `validate=False` 并返回 `APPROVAL_CONTEXT_MISMATCH`；legacy 审批不得进入 APPROVED 可用态；审批审计需落库（approval_id/run_id/approver/expires/fingerprint）。
- **回滚/缓解**：先在 `context` 增加 `run_id` 并纳入 fingerprint（需同步改 `SafeAgent`/`PolicyEngine` 调用方），保留一次性 consume；不改动现有 TTL 默认 300s。
- **归属任务**：HC-02 与 HC-07（审计持久化）。

### SEC-05（P1，CWE-345/CWE-613）Java TeamAgentRun grant 的绑定与一次性语义不完整

- **影响**：已有正确方向（服务端计算 digest、审批人不得自批、条件 UPDATE 原子消费），但：
  1. `grant_token` 生成并落库后**从未校验**（消费时直接置 NULL），"签名 grant"名义存在、实际不参与鉴权；持有 runId + 同用户 session 即可执行。
  2. digest 基于渲染后的命令文本，而不是规范化 `parameters_json` + 工具版本；若渲染逻辑/工具实现变化而命令文本相同，无法证明"审批的就是将要执行的"。
  3. 无审批取消/撤回状态、无创建幂等键；同一请求重复创建 run 会产生多条待审记录。
  4. 审计表只记 runId/actor/basis（`TeamAgentRunService.java:166`），不记 digest，事后无法证明绑定。
- **证据**：
  - `TeamAgentRunService.java:120-126`（preview 计算 digest）。
  - `TeamAgentRunService.java:148-168`（approve、自批禁止、300s 过期、写 basis）。
  - `TeamAgentRunService.java:160-164`（token/expiry 生成）。
  - `TeamAgentRunService.java:184-206`（consumeGrant：195-197 digest 比较，198-200 过期，201-203 原子 UPDATE 并置空 token；无 token 校验）。
  - `TeamAgentRunController.java:71-83`（preview 由服务端生成 digest）；`85-112`（execute 重新计算 digest）。
- **复现输入**：本地对已 approve 的 run：a) 不带 `grantToken` 调 execute；b) 连续两次 execute；c) 用 fixture 直接改 `parameters_json` 后 execute。当前 a 成功、b 第二次 409、c 409。
- **预期拒绝**：a 应 409 `GRANT_TOKEN_REQUIRED`；b 仅一次 200；c 409 `TEAM_RUN_PREVIEW_CHANGED`；审计必须存 digest 与 approver。
- **回滚/缓解**：若启用 token 校验导致旧前端不兼容，可先服务端强制 `requireToken` 并保留一次性消费；不得回退为只凭 runId。
- **归属任务**：HC-02 提整改单；HC-01 定义审批记录字段。

### SEC-06（P0，CWE-918）F06 爬取 SSRF

- **影响**：`publicTarget` 只检查 URL 主机字符串，不做 DNS 解析、不做连接期 IP 固定。可被以下形式绕过并访问内网/元数据服务：
  - `http://localhost.:8080/`（尾点，`startsWith("localhost")` 为 true，但 `uri.getHost()` 常返回 `localhost.`，`equals("localhost")` 为 false；`endsWith(".localhost")` 也为 false）。
  - `http://[::ffff:127.0.0.1]:8080/`（IPv4-mapped IPv6，去括号后为 `::ffff:127.0.0.1`，不匹配 `::1`/`127.*`）。
  - IPv6 未覆盖：`fe80::/10`、`fc00::/7`、`::`、`2001:db8::` 等。
  - 未覆盖私有段：`100.64.0.0/10`（CGNAT）、`198.18.0.0/15`、`0.0.0.1` 等。
  - DNS rebinding：校验时解析为公网，连接时解析到内网（代码没有 pin 已解析地址）。
  - **首跳不复检**：`run()` 直接把数据库中的 `seedUrl` 入队，`fetch()` 只对重定向 Location 复检（`188-195`），迁移前/被篡改的 seed 记录可直连内网。
  - 重定向最多 4 跳且逐跳检查，但每跳仍是字符串检查，配合 DNS 可绕过。
- **其他边界缺陷**：`BodyHandlers.ofString()` 一次性读全响应（无 Content-Length/字节上限）；`maxPages<=50` 但无全局限速/单用户并发限制，仅每页 `sleep(300ms)`；单请求超时 8s 只限制单跳，50 页 × 多跳可长时间占用线程。
- **证据**：
  - `KnowledgeCrawlService.java:291-300`（`publicTarget` 字符串判断）。
  - `KnowledgeCrawlService.java:275-289`（创建时唯一一次校验）。
  - `KnowledgeCrawlService.java:170-199`（`run`/`fetch`；首跳 `uri` 未调用 `publicTarget`）。
  - `KnowledgeCrawlService.java:185`（`BodyHandlers.ofString` 无上限）。
  - `KnowledgeCrawlService.java:188-195`（重定向手写循环、逐跳检查）。
  - `KnowledgeCrawlService.java:69-70`（`maxPages` 上限 50）。
  - `KnowledgeCrawlService.java:130-137`（固定 300ms 间隔）。
  - `KnowledgeCrawlService.java:117-121`（链接仅允许同 seedHost，属正向保护）。
- **复现输入（全部指向本地 mock 服务，禁止真实外网）**：创建 source 时填 `http://localhost.:18080/`、`http://[::ffff:127.0.0.1]:18080/`、`http://100.64.0.1:18080/`；本地 mock 返回 302 → `http://127.0.0.1:18080/`；mock 以 1 字节/秒吐 60 秒；mock 返回 200MB body。
- **预期拒绝**：创建与每跳 fetch 均返回 400 `CRAWL_URL_BLOCKED`（含解析后 IP 与命中规则）；响应体超限返回 413/截断并记录；慢速在总超时内中止；同一用户并发 run 受限（429）。
- **回滚/缓解**：如短时间无法完成 DNS/IP 校验，先把爬取开关默认关闭（`KNOWLEDGE_CRAWL_ENABLED=false`），并清空/禁用历史 seed；不得只扩大黑名单。
- **归属任务**：HC-02（本任务）→ 后续 IMPLEMENT；HC-04 知识侧配合。

### SEC-07（P0，CWE-269/CWE-863）管理权限在 DB 异常/缺 profile 时沿用历史 admin/ROOT 兼容语义

- **影响**：
  1. `hasPlatformCapability` 在 `platform_admin_profile` 缺少当前账号行时直接返回 `true`（全部能力）——任何被提升为 admin 但未写入 profile 的账号等价 ROOT。
  2. `createAccount` 只写 `app_user`，不写 `platform_admin_profile`；`updateRole` 提升为 admin 时同样不写 → **新管理员天然全能力**，且不受能力列表约束。
  3. `platformLevel` 在 profile 缺失时返回 `"ROOT"`；`platformAdministrators` 在查询异常时把全部 admin 当作 `root` 返回（fail-open 展示）。
  4. 真正 DB 异常时 `hasPlatformCapability` 抛 500（fail-closed，属正确），但上述"缺行即全能力"是逻辑 fail-open，与 DB 异常无关。
- **证据**：
  - `UserAccountService.java:120-134`（129-130：`levels.isEmpty()` → `return true`；133：能力查询）。
  - `UserAccountService.java:208-218`（216-217：无 profile → `ROOT`）。
  - `UserAccountService.java:246-258`（`createAccount` 无 profile INSERT）。
  - `UserAccountService.java:262-273`（提升为 admin 仅改 `app_user.role`）。
  - `UserAccountService.java:140-148`（146-148：异常时回退所有 admin 为 root）。
  - `PlatformAdminGovernance.java:12-14`（ROOT = 全部能力）。
- **复现输入（本地 H2/测试替身）**：a) 以 admin 会话调用任一能力门禁接口（如平台管理员列表/治理写操作）；b) 用 mock `JdbcTemplate` 抛 `DataAccessException` 调 `hasPlatformCapability`；c) 新建 admin 后查询 `platform_admin_profile` 是否为空。
- **预期拒绝**：缺 profile 的普通 admin 只能拥有最小只读能力（403 其他能力）；治理表故障返回 503 且不授予任何提升；被提升账号必须显式写 profile（默认空能力）。
- **回滚/缓解**：如担心上线阻断历史管理员，使用**迁移期显式 allowlist**（按 user_id 白名单一次性授予）而非"缺行即全能力"；必须能在不改数据的情况下回退为只读。
- **归属任务**：HC-02 P0 单；数据迁移与 HC-01/数据库 owner 协同。

### SEC-08（P1，CWE-639/CWE-284）Server/Inspector 查询无统一 scope，Loop 全局事件投影

- **影响**：
  1. 任意登录用户可列举全部服务器、指标（无 owner/team 过滤），跨用户泄露主机名、IP、负载。
  2. `GET /api/inspector/events` 返回全局巡检事件（表中无 owner 列），任意用户可读他人资产巡检结果、建议与 evidence。
  3. 决策闭环 `GET /api/agent/loops` 会把**全局** inspector 事件同步进当前用户自己的闭环（`source_ref` 去重），造成跨用户数据投影 + 重复学习（见 SEC-10）。
  4. `X-User-Id` 在多处 controller 直接读取（`defaultValue="1"`），当前靠 `TrustedUserIdFilter` 兜底；scope 设计未统一到 principal。
- **证据**：
  - `ServerController.java:36-47`（GET 列表/详情无 scope）。
  - `ServerMetricController.java:30-46`（指标无 scope）。
  - `InspectorController.java:22-35`（事件查询无 principal 校验）。
  - `InspectorEventService.java:28-47`（直接查全表）。
  - `backend/src/main/resources/db/migration/V20261002__operations_and_accounts.sql:3`（`inspector_event` 无 user/team 列）。
  - `DecisionLoopService.java:171-180`（全量读取 + 按 `source_ref` 去重后写入当前用户）。
  - `DecisionLoopController.java:18-23`（`X-User-Id` 默认 1）。
- **复现输入**：用户 A 无服务器数据；用户 B 造 1 条 inspector 事件后，A 调 `GET /api/servers`、`GET /api/inspector/events`、`GET /api/agent/loops`。
- **预期拒绝**：无 team/owner 绑定返回空列表或 403；闭环同步只能消费与当前用户/团队关联的事件；`X-User-Id` 只在无 session 的受控内部路径可用。
- **回滚/缓解**：先加读侧 team 过滤（不写数据），再补 `inspector_event` 归属列；迁移期保留全局只读视图仅供审计管理员（独立端点 + 审计日志）。
- **归属任务**：HC-01（数据模型）+ HC-02（scope 规则）。

### SEC-09（P1，CWE-362）`MAX(id)` 取刚插入 ID 的同 owner 并发歧义

- **影响**：创建库/条目/记忆/source 后，用 `MAX(id)` 反查刚插入行；并发创建（同一 user）时可能取到另一条更高 id，导致返回他人（同用户）记录内容，或后续更新写错对象。**不造成跨用户越权**（SQL 带 `user_id`），但会破坏"创建返回自己的对象"契约与审计一致性。
- **证据**：
  - `PersonalKnowledgeService.java:40`（`MAX(id) WHERE user_id` 取库）。
  - `PersonalKnowledgeService.java:104`（`MAX(id) WHERE user_id AND library_id` 取条目）。
  - `OperatorMemoryService.java:22`、`OperatorMemoryService.java:49`（记忆 id 反查）。
  - `KnowledgeCrawlService.java:73`（source id 反查）。
  - 正确模式对照：`TeamAgentRunService.java:75-86`、`JdbcOperationRunRecorder.java:23-39` 使用 `GeneratedKeyHolder`。
- **复现输入**：本地并发（两线程/两请求）同一用户连续创建两条知识条目；断言行 A 返回 id 是否等于 A 自己的插入 id（用唯一标题校验）。
- **预期拒绝**：创建必须返回本次插入的主键（`GeneratedKeyHolder`/`RETURNING`），或以业务唯一键回查；并发下不得返回他人记录。
- **回滚/缓解**：改动局限在创建返回路径，不改变表结构。
- **归属任务**：HC-01。

### SEC-10（P1，CWE-837/CWE-362）重复 review/GET 同步导致重复 learn 与 memory feedback

- **影响**：
  1. 每次 `POST /api/agent/loops/{id}/review` 都无条件 `learn()`：重复 review 会重复创建 learned memory、累加 `learned_count`、抬高 `confidence`，形成"刷复盘=刷置信度"。
  2. `syncFromInspector` 以 `NOT EXISTS source_ref` 去重，但表**无唯一索引**，两个并发 GET 可同时通过检查插入重复 loop；重复 review 亦重复 feedback。
  3. 全局事件投影（SEC-08）会让每个用户首次 GET 都复制一份全局事件，进一步放大重复与数据污染。
- **证据**：
  - `DecisionLoopService.java:141-153`（review 更新后直接 `learn`，无幂等判断）。
  - `DecisionLoopService.java:171-180`（`NOT EXISTS` + 插入，无唯一约束）。
  - `DecisionLoopService.java:204-211`（sync 后逐条 learn）。
  - `DecisionLoopService.java:216-249`（learn 每次新建记忆；234-240 插入 learned memory）。
  - `backend/src/main/resources/db/migration/V20261024__agent_decision_loop.sql:27-28`（仅普通索引，无 `(user_id, source_type, source_ref)` 唯一键）。
- **复现输入**：同一 loop 连续 5 次 review；两个并发 GET `/api/agent/loops`（前置 1 条全局 inspector 事件）；断言 learned_count、memory 行数、loop 行数。
- **预期拒绝**：同一 loop 同一 stage 的 review 幂等（第二次 200 但 `learned=false` 或 409）；同步以唯一键 upsert；learn 以 `(user, source_ref, lesson_hash)` 去重。
- **回滚/缓解**：先做应用层幂等，再加唯一索引（需评估历史重复数据清理）。
- **归属任务**：HC-01 / HC-07。

### SEC-11（P1，CWE-532/CWE-312）日志/Prompt/凭据泄漏面

- **影响**：
  1. `OperationToolService` 把原始 stdout/stderr 直接交给 recorder 落库，API 可读回；`OperationRedactor` 仅在 SSH/WS 路径使用，且只覆盖 `key=value` 简单形态，无法覆盖 `Bearer <token>`、JSON、base64、多行 env。执行 `env`/`cat .env`/`docker inspect` 即可把凭据明文写入数据库与前端。
  2. 爬取失败原因 `last_error` 落库并回显（含内部主机/异常细节）；抓取正文以 Markdown 明文入库（可能含页面中的个人信息/密钥）。
  3. 巡检 evidence 原样落库（`inspector_evidence.content`），无分类与脱敏。
  4. 管理二次确认口令通过 `X-Admin-Password` 请求头传输；nginx access 日志记录完整 request line（含 query），若 token 放 query 会落日志。
  5. 聊天日志目前只记录 ID（`ai-service/app/services/chat.py:63-66`、`242-245`），属正向保护；但 tool_calls/inspector evidence 会带输出内容，需单独约束。
- **证据**：
  - `JdbcOperationRunRecorder.java:45-50`（stdout/stderr 原样 INSERT）。
  - `OperationToolService.java:189-192`（执行结果直接 `recordCommand`，未调用 redactor）。
  - `OperationRedactor.java:6-14`（仅窄正则，`key=value`）。
  - `SshConnectionAdapter.java:203-207`（仅 SSH 路径调用脱敏）。
  - `OperationRunQueryService.java:54-56`（原样读回 stdout/stderr）。
  - `KnowledgeCrawlService.java:128`、`KnowledgeCrawlService.java:140-141`（错误信息落库）。
  - `KnowledgeCrawlService.java:165-166`（抓取正文入库）。
  - `InspectorEventService.java:114-119`（evidence 原样落库）。
  - `deploy/nginx/nginx.conf:68-79`（access log 含 request）。
  - `AdminConfirmationFilter.java:28`（口令走请求头）。
- **复现输入**：本地工具输出固定 fixture `API_TOKEN=abc123` / `Authorization: Bearer xyz`；爬取本地 mock 页面含 `email=...`；调 run 详情接口与查库。
- **预期拒绝**：落库/回显前统一脱敏为 `[REDACTED]`（至少覆盖 `password/token/secret/api_key/authorization/cookie/private_key` 与 Bearer/JSON 形态）；爬取正文只存正文，不存 Cookie/Header；日志不记录请求头与正文。
- **回滚/缓解**：先加"写库前统一 redactor"，再做历史数据清洗；保留原始输出仅限本地调试开关且默认关。
- **归属任务**：HC-02 + HC-05（日志/部署）+ HC-07（证据）。

### SEC-12（P1，CWE-306）Knowledge `/api/search` 默认开放

- **影响**：`KNOWLEDGE_API_KEY` 未配置时 `require_api_key` 直接放行；知识服务默认监听 0.0.0.0:8002。匿名可检索全部私有知识库内容；若同时 `ALLOW_INGEST=1`，匿名可写入/污染知识库，影响 RAG 输出与后续决策。
- **证据**：
  - `knowledge/server.py:91-103`（未配置 key 时不校验）。
  - `knowledge/server.py:112-115`（`/api/search` 依赖）。
  - `knowledge/server.py:258`（health 暴露 `auth_required`）。
  - `knowledge/server.py:22`（`ALLOW_INGEST` 环境开关）。
  - `ai-service/app/services/rag.py:61-62`（仅配置 key 时才带 `X-API-Key`）。
- **复现输入**：不设置 `KNOWLEDGE_API_KEY` 启动（本次不启动，仅本地测试用例描述），`POST http://127.0.0.1:8002/api/search {"query":"..."}` 不带 key；另设 `ALLOW_INGEST=1` 调 `/api/documents`。
- **预期拒绝**：未配置 key 时拒绝启动或要求显式 `KNOWLEDGE_ALLOW_ANONYMOUS=true` 且仅绑定 127.0.0.1；ingest 永不允许匿名。
- **回滚/缓解**：优先改部署（设 key + 内网绑定），代码改造成"未配置即 fail-closed"需与 HC-04 协同。
- **归属任务**：HC-04 / HC-02。

### SEC-13（P1，CWE-798/CWE-1188）部署默认凭据与端口发布

- **影响**：默认/示例口令直接可登录或连接；数据库、Redis 端口发布到宿主；本地固定加密密钥用于凭据加密；生产未强制覆盖则整体失守。属部署面 P1，需 HC-05 修复。
- **证据**：
  - `backend/src/main/resources/application-prod.yml:7-9`（`MYSQL_USERNAME:root`，`MYSQL_PASSWORD:` 空默认）。
  - `deploy/docker/docker-compose.yml:44`、`50`（`change-me-root-password`）。
  - `deploy/docker/docker-compose.yml:55-58`（3306 端口发布）。
  - `deploy/docker/docker-compose.yml:111-113`（6379 端口发布）。
  - `deploy/docker/redis/conf/redis.conf:9`（`bind 0.0.0.0`；全文件检索未发现 `requirepass`）。
  - `backend/src/main/resources/application-local.yml:61`（固定的本地 AES key）。
  - `backend/src/main/resources/application.yml:67-69`（bootstrap 管理员口令可空，需显式环境变量）。
- **复现输入**：静态配置核对；本地起 compose 后 `redis-cli -h 127.0.0.1 ping`（未来 RUN 用，本次不执行）。
- **预期拒绝**：启动预检发现默认口令/发布端口即失败；Redis 必设 `requirepass` 且不发布宿主；prod 必须由 secret 注入。
- **回滚/缓解**：仅改部署与环境变量，代码无回滚需求。
- **归属任务**：HC-05；HC-02 只登记。

### SEC-14（P2，CWE-918）模型连接 baseUrl 内网 SSRF

- **影响**：任意已认证用户可创建 `baseUrl` 指向任意 http(s) 地址的模型连接（无私有地址校验）；调用 `/runtime|invoke` 受内部 token 保护，因此从浏览器直接利用的可能性低，但一旦内部 agent 使用该连接，会把请求发往内网/元数据地址并可能回显响应。属二级 SSRF 面。
- **证据**：
  - `ModelConnectionService.java:322-339`（仅 trim/去尾斜杠，无 host 校验）。
  - `ModelProviderClient.java:85-96`（按 `URI.create(baseUrl + path).toURL()` 发请求，任意 host）。
  - `ModelConnectionController.java:40-58`（创建/更新仅需登录，无管理员限制）。
  - `SecurityConfig.java:31`、`SecurityConfig.java:54`（`/runtime|invoke` 在内部 token 路径）。
  - `InternalTokenAuthenticationFilter.java:33-43`（内部 token 覆盖路径）。
- **复现输入**：登录用户创建 baseUrl=`http://127.0.0.1:18080/v1`，随后（fixture 直接调用）带内部 token 调 `/api/model-connections/{id}/runtime`。
- **预期拒绝**：创建/更新时拒绝私有/回环/非 http(s) 地址（与爬取共用 IP 校验）；或仅管理员可创建。
- **回滚/缓解**：先在服务层加 host 校验，不改表结构；已存在的恶意连接需清理任务。
- **归属任务**：HC-02；与 SEC-06 共用校验工具。

### SEC-15（P2，CWE-639/CWE-807）内部 token 覆盖面窄 + `X-User-Id` 遗留头

- **影响**：内部 token 仅覆盖 5 条路径，其余内部语义端点若被误配为 `permitAll`，就会退化为"无认证 + 信任客户端头"。当前 `TrustedUserIdFilter` 在 `SessionUser` 上覆盖头值，普通 session 请求不可直接越权；但 `defaultValue="1"` 使"principal 非 SessionUser 且未拒绝"时默认落到 user 1。属潜在 IDOR 面，需在统一 principal 改造中消除。
- **证据**：
  - `TrustedUserIdFilter.java:18-28`（仅覆盖，不拒绝头）。
  - `InternalTokenAuthenticationFilter.java:33-43`（路径枚举）。
  - `SecurityConfig.java:52-62`（`anyRequest` 与 permitAll 清单）。
  - `DecisionLoopController.java:20`、`OperationRunController.java:23`（`X-User-Id` 默认 1）。
- **复现输入**：已登录用户 A 请求头带 `X-User-Id: 999` 调列表/创建接口，断言实际落库 `user_id == A`；匿名请求同头断言 401。
- **预期拒绝**：不读取客户端用户头（一律 principal）；内部调用使用独立 token + 显式 `onBehalfOf` 字段并审计。
- **回滚/缓解**：可分批替换 controller 取用户方式，保留 filter 作为兜底，不回退。
- **归属任务**：HC-01/HC-02。

---

## 3. 与交接书/基线的一致性

- F03（聊天无 Java 认证）、F06（爬取 SSRF）、审批绑定缺口均在交接书 F 列表范围内；本文件新增可精确派单的子缺陷：SEC-03（MultiExec 同一 nonce 自批）、SEC-07（无 profile 即全能力）、SEC-09（`MAX(id)`）、SEC-14（模型连接 SSRF）。
- 与 `route-map.md` 一致：`/ai-api` 为 ai-service 直连、`/api` 走 Java session、Knowledge 仅在配置 key 时校验。
- 与 `status-baseline.md` 一致：未启动服务、未跑测试；本文所有"当前行为"均为静态推导，实际运行行为在 RUN 阶段验证。
- 本文不含任何已利用结论；SEC-06 的绕过形式均为代码级推导，标注"未做故障注入"。
