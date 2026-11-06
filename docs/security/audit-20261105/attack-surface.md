# HC-02 攻击面清单（入口 × 认证现状 × 信任边界）

- 审计日期：2026-11-05
- 方式：静态只读；未启动服务、未探测端口、未调用真实接口。认证现状指"代码中是否存在校验"，不代表线上网关实际配置。
- 与 `docs/audit/20261105/route-map.md` 的路径/端口事实一致，不重复求证，只补充认证与边界结论。
- 状态：**有** = 存在强制认证/授权；**无** = 无认证；**部分** = 仅特定配置/路径校验；**UNKNOWN** = 依赖部署或运行时，本次未验证。
- 注：审计开始时 `ai-service/app/**` 可读，中途被并行改动移出主工作树；其中行号以审计快照为准，IMPLEMENT 前需复核。

## 1. 信任区定义

| 区域 | 组件 | 信任级别 | 说明 |
| --- | --- | --- | --- |
| Z0 不可信 | 浏览器、公网客户端 | 不可信 | 可伪造任意 header、body、`X-User-Id`、`X-Run-ID` |
| Z1 Java 边缘 | nginx `/api` + Spring Security | 边界 | session cookie + CSRF；`TrustedUserIdFilter` 覆盖用户头 |
| Z2 ai-service | FastAPI `:8001` + nginx `/ai-api` | **当前等同公网** | 无身份依赖，只有 CORS/请求体限制 |
| Z3 Knowledge | FastAPI `:8002` | 内网（默认） | 仅 `KNOWLEDGE_API_KEY` 可选校验；nginx 未直接暴露 |
| Z4 Agent 库 | `agent/`（进程内） | 宿主可信 | 审批人身份由宿主传入；无独立网络入口 |
| Z5 执行器 | Java Operations / SSH / 终端 WS | 高敏 | 可执行命令；依赖 session + runtime ownership |
| Z6 管理端 | `/api/admin/**`、平台治理 | 最高 | session + admin 角色 + `X-Admin-Password` + CSRF |
| Z7 基础设施 | MySQL/Redis/内部 token | 最高 | docker 端口与默认口令决定实际暴露面 |
| Z8 出站 | 爬取/模型连接 | 边界 | 可被诱导访问内网（SSRF） |

## 2. 入口清单总表

| # | 入口 | 协议/路径 | 认证现状 | 授权/边界要点 | 关联风险 |
| --- | --- | --- | --- | --- | --- |
| E01 | 浏览器聊天 | `POST /ai/api/chat/stream`（默认 `/ai`；生产可 `VITE_AI_SERVICE_URL=/ai-api`） | **无** | 无 subject、无 run 所有权；nginx `/ai-api` 直通 | SEC-01/02 |
| E02 | 浏览器聊天（非流式） | `POST :8001/api/chat` | **无** | 同上，可被脚本直接调用 | SEC-01/02 |
| E03 | ai-service 健康 | `GET :8001/api/health`、`/api/chat/health` | **无** | 仅暴露状态；不应泄露内部地址/版本细节 | SEC-11 |
| E04 | Java API 会话 | `/api/**`（cookie `SMARTOPS_SESSION`） | **有** | `anyRequest().authenticated()`；登录/匿名会话/CSRF 除外 | 基线 |
| E05 | 匿名会话/CSRF | `/api/auth/session`、`/api/auth/csrf` | **无**（permitAll） | 只发匿名 token/CSRF，不含用户数据 | 低 |
| E06 | 登录/登出 | `/api/auth/login|logout` | 登录无（公开）、登出按 session | 登录有失败计数（`AuthService`，阈值 UNKNOWN） | 低 |
| E07 | OpenAI 兼容网关 | `/v1/models`、`/v1/chat/completions` | **部分** | permitAll + 强制 Bearer key（`ModelGatewayController.java:167-193`）；忽略 CSRF 因非 cookie | 低 |
| E08 | 内部 token 入口 | `/api/model-connections/*/runtime|invoke`、`/api/inspector/check|verify|replan` | **有**（token） | `InternalTokenAuthenticationFilter` fail-closed；无 session 权限提升；`internal-bypass` 默认 false | 部署 token 管理 |
| E09 | 管理端写操作 | `/api/admin/**` 等 | **有** | session + role=admin + `X-Admin-Password` + CSRF | SEC-07/13 |
| E10 | 服务器/指标查询 | `GET /api/servers`、`/api/servers/{id}/metrics` | **有**（仅登录） | 无 owner/team scope，读侧全局 | SEC-08 |
| E11 | Inspector 查询 | `GET /api/inspector/events|summary` | **有**（仅登录） | 全局事件，无主体过滤 | SEC-08 |
| E12 | Inspector 写入 | `POST /api/inspector/check|verify|replan` | **有**（内部 token） | `event.id`/`task_id` 由调用方控制，可覆盖/伪造归属 | SEC-02/08 |
| E13 | 决策闭环 | `/api/agent/loops/**` | **有**（仅登录） | 读写按 user_id 过滤；同步却读全局 inspector | SEC-08/10 |
| E14 | 个人知识 | `/api/knowledge/**` | **有**（仅登录） | 按 user_id 过滤；创建用 `MAX(id)` 反查 | SEC-09 |
| E15 | 运维执行 | `/api/operations/tools/*`、`/api/operations/multi-exec/*` | **有**（仅登录） | `OperationToolService.java:160` runtime ownership；审批/只读门禁 | SEC-03/05/11 |
| E16 | 运维 run 详情 | `/api/operations/runs/**` | **有**（仅登录） | 按 user_id 查 run；输出明文 | SEC-11 |
| E17 | SSH/终端 WS | `/ws/operations/terminal` | **有**（session+二次校验） | Origin 仅 localhost；生产域名收窄 UNKNOWN | 低 |
| E18 | 模型连接 | `/api/model-connections/**` | **有**（仅登录） | 创建任意 baseUrl；调用需内部 token | SEC-14 |
| E19 | 知识检索 | `POST :8002/api/search` | **部分** | 未配置 `KNOWLEDGE_API_KEY` 即开放 | SEC-12 |
| E20 | 知识写入 | `POST :8002/api/documents` | **部分** | `ALLOW_INGEST=1` 时允许 ingest；否则拒绝 | SEC-12 |
| E21 | 知识健康 | `GET :8002/health` | **无** | 返回 `auth_required` 等配置状态 | 低 |
| E22 | 爬取管理 | `/api/knowledge/crawl/sources/**` | **有**（仅登录） | 创建 URL 仅字符串校验；run 可同步发大量出站请求 | SEC-06 |
| E23 | 爬取出站 | 任意用户 URL → `HttpClient` | 不适用 | 字符串黑名单、无 DNS/IP 固定、无下载上限 | SEC-06 |
| E24 | 模型出站 | `ModelProviderClient` → baseUrl | 不适用 | 任意 http(s) host | SEC-14 |
| E25 | MySQL | `:3306`（compose 发布） | **UNKNOWN/弱** | 默认 root + change-me；prod 可空密码 | SEC-13 |
| E26 | Redis | `:6379`（compose 发布） | **无**（未发现 requirepass） | `bind 0.0.0.0`，端口发布 | SEC-13 |
| E27 | nginx 管理/静态 | `:80/443` + `/ai-api` | 静态无、`/ai-api` 无 | access log 含完整 request line | SEC-01/11 |

## 3. 关键入口详情

### E01/E02 ai-service 聊天（无认证）

- `ai-service/app/api/chat.py:42-61`（`/api/chat`）、`64-99`（`/api/chat/stream`）仅注入 `ChatService`，无 `Depends(require_user)`。
- `ai-service/app/schemas/chat.py` 无 user/tenant 字段；`ChatRequest.message` 是唯一业务输入。
- 身份来源：`ai-service/app/core/correlation.py:36-46` 仅取 `X-Request-ID`/`X-Task-ID`/`X-Run-ID`，均客户端值。
- 边界：nginx `/ai-api` 无 `auth_request`（`deploy/nginx/nginx.conf:199-212`）；vite 开发代理 `/ai` 仅本地便利（`frontend/vite.shared.mjs:19-24`），生产不应复用；`frontend/src/api/stream.ts:8` 的 `AI_SERVICE_BASE` 若生产配 `/ai-api` 则直连暴露。
- 结论：**Z2 实际位于 Z0**；认证补齐前，"仅内网"假设不成立。

### E04 Java API 会话（有认证）

- `SecurityConfig.java:52-62`：`anyRequest().authenticated()`；permitAll 仅 E03/E05/E06/E07/E08；CSRF 仅对网关/内部路径/图形点选忽略（`SecurityConfig.java:47-50`）。
- `TrustedUserIdFilter.java:18-28`：只覆盖 `SessionUser` 的 `X-User-Id`，不拒绝自定义头；未来 principal 类型变化需显式拒绝。
- `AccountStateFilter.java:20-38` 每请求校验账号可用/会话版本/改密状态，属正向保护。

### E05/E06 认证边缘

- 匿名会话 permitAll 是 CSRF/session 机制的一部分，不返回用户数据；需确保不被复用为"已认证"。
- 登录失败计数/锁定在 `AuthService`（本次未逐行审计，阈值/解锁策略 UNKNOWN），不作为本次 P0。

### E07 OpenAI 兼容网关（部分认证）

- permitAll 但 handler 校验 `Authorization: Bearer` 与网关 key（`ModelGatewayController.java:167-193`）；`SecurityConfig.java:47` 忽略 CSRF 合理。
- UNKNOWN：网关 key 存储/轮换、是否允许枚举 `/v1/models`、key 为空时的启动行为。

### E08 内部 token（有认证、fail-closed）

- `InternalTokenAuthenticationFilter.java:33-43` 仅 5 条路径；`56-59` token 未配置 503，缺失/错误 401。
- 边界：共享密钥、无调用方身份；泄漏即可写 inspector 事件、触发模型连接。建议加调用方标识与审计。
- 风险：路径枚举式保护，新增内部端点忘记加前缀/过滤就退回 session/permitAll（SEC-15）。

### E10/E11 服务器与 Inspector 读（仅登录，无 scope）

- `ServerController.java:36-47`、`ServerMetricController.java:30-46` 直接返回全局；`inspector_event` 无 owner 列（`V20261002__operations_and_accounts.sql:3`）。
- 边界："已认证用户"与"资产所属用户/团队"之间的缺口；写操作有 ADMIN 限制（`SecurityConfig.java:58-61`），读没有。
- 结论：**认证 ≠ 授权**；需 HC-01 定义资产/团队 scope。

### E12 Inspector 写入（内部 token，内容可伪造）

- `InspectorEventService.java:92-102`（按 `event.id()` 插入）、`114-119`（evidence 原样写入）。
- 调用方可指定任意 `id`/`task_id`/`target`，无 idempotency、无 owner；token 泄漏可批量污染事件/证据（SEC-02/08/11）。

### E13–E16 用户侧业务面

- E13 读侧按 user_id；`syncFromInspector` 全量读（`171-180`）→ 跨用户投影。
- E14 按 user_id；创建 `MAX(id)` 反查（`PersonalKnowledgeService.java:40,104`）。
- E15 `OperationToolService.java:160` 要求 runtime ownership；审批两套实现语义不一致（SEC-03/05）。
- E16 按 user_id（`OperationRunQueryService.java:42-57`），输出未脱敏（SEC-11）。

### E17 终端 WebSocket（有认证）

- `AuthenticatedSessionHandshakeInterceptor.java:18-28` 要求 session；`OperationsTerminalWebSocketHandler.java:62-72` 校验用户/账号状态/MFA；`OperationsWebSocketConfig.java:18-22` Origin 仅 localhost。生产白名单 UNKNOWN。
- 现有保护充分；整改时不得因"聊天统一网关"移除 WS 二次校验。

### E18 模型连接（有登录、无管理员限制）

- `ModelConnectionController.java:40-58` 任何登录用户可创建/更新；`ModelConnectionService.java:322-339` 仅规范 baseUrl 字符串。
- 调用入口 E08 受内部 token 保护，浏览器直接 SSRF 不可达；内部 agent 可被诱导（SEC-14，P2/UNKNOWN）。

### E19–E21 Knowledge（默认开放）

- `knowledge/server.py:95-109` 未配置 key 直接通过；`112-115` search；`22` `ALLOW_INGEST`；`258` health 暴露 `auth_required`。
- Knowledge 位于内网，但 ai-service 无认证 → Z0 可经 RAG 间接读其内容，数据边界已被 E01 击穿。

### E22–E23 爬取（有登录、出站无边界）

- 管理入口需 session；出站 `KnowledgeCrawlService.java:170-199` 用 Java `HttpClient`，`publicTarget` 仅字符串（`291-300`）。
- Java 侧唯一"用户可控 URL → 服务端出站"高频路径，SSRF 优先级最高（SEC-06）。

### E24 模型出站

- `ModelProviderClient.java:85-96` 仅校验 scheme/host 非空；无内网限制（SEC-14）。

### E25–E27 基础设施与 nginx

- `deploy/docker/docker-compose.yml:44,50,55-58,111-113` 默认口令、3306/6379 发布；`deploy/docker/redis/conf/redis.conf:9` `bind 0.0.0.0`。
- `deploy/nginx/nginx.conf:68-79` access log 含请求行；`199-212` `/ai-api` 直通。
- 部署面可绕过应用层全部认证（直连 DB/Redis）；HC-05 优先，本次只登记（SEC-13）。

## 4. 跨边界数据流

1. **浏览器 → ai-service**：无认证，body 任意；回程 SSE 含模型输出与 RAG 片段（可能含其他用户知识）。**当前最大缺口**。
2. **ai-service → Knowledge**：`X-API-Key` 可选；ai-service 被匿名可达 → 知识库读权限被继承。
3. **Java → ai-service**：未发现 Java 反向调用 ai-service；拆分部署时无 service-to-service 认证，UNKNOWN。
4. **Java → 出站**：爬取/模型连接，用户可控 URL；需统一 SSRF 校验（SEC-06/14）。
5. **agent（进程内） → 执行器**：approval 由宿主传入 reviewer 字符串；无网络入口，信任=宿主；接 HTTP 时必须补主体认证（SEC-04）。
6. **内部 agent → Java 内部 token**：共享密钥、无调用方身份；泄漏等于 inspector 写权限（E08/E12）。

## 5. 仍为 UNKNOWN

- 生产 nginx 是否额外加 `auth_request`/mTLS/WAF（route-map UNKNOWN #1）；本次只按仓库配置判断。
- ai-service 生产是否只监听内网/云安全组限制；仓库默认 0.0.0.0。
- 内部 token 的实际分发方式、轮换周期、是否按调用方分 key。
- 终端 WS 生产 Origin 白名单是否配置域名（默认 localhost）。
- `operation_credential` 生产加密密钥是否由外部 KMS 注入（local 固定 key）。
- Agent `ApprovalManager` 是否有外部持久化审计（仓库内仅内存）。
- Knowledge `ALLOW_INGEST` 生产取值、`KNOWLEDGE_API_KEY` 是否必设。
- 审计中途 ai-service 源码被移出主工作树：是否为并行改动/稀疏检出，以及最终路径与行号（BLOCKED，待复核）。
