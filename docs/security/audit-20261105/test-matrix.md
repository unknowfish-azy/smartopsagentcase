# HC-02 安全负例测试矩阵（本地可复现，禁止真实外网攻击）

- 日期：2026-11-05
- 状态：**仅设计，未执行**。本次不启动服务、不跑 pytest/mvn/npm、不连接真实数据库。
- 安全护栏：
  1. 仅访问 `127.0.0.1`/`localhost` 上自建 mock 与本地测试库/H2；禁止向真实第三方域名/IP 发包。
  2. SSRF 用例的外部目标全部是本地 mock（如 `127.0.0.1:18080`）；"内网目标"也用本地端口模拟，不扫描真实网段。
  3. DNS 变化只在测试进程内用 `127.0.0.1` mock DNS/可注入 Resolver，禁改生产 DNS。
  4. 超大 body/slow-drip 由本地 mock 生成，限制本机资源，设置总时长与最大字节。
  5. 证据只保存脱敏后的响应/日志/DB 行，不保存真实凭据。
- 运行形态：Spring `@SpringBootTest`（H2/mock JdbcTemplate）或 `MockMvc`；Python `pytest` + `TestClient`；SSRF 用 `WireMock`/`http.server`；时间用 `Clock`（`TeamAgentRunService.java:43-57` 包内构造器、`agent/safety/approval.py:37-40` 的 `clock`）。

## 1. 用例总表

| ID | 覆盖风险 | 场景 | 预期拒绝（整改后） | 证据保存 |
| --- | --- | --- | --- | --- |
| TM-01 | SEC-01 | 匿名调用 8001 `/api/chat` | 401/403 | 请求、响应 status/body、拒绝日志（无 message 正文） |
| TM-02 | SEC-01 | 匿名调用 `/ai-api/chat/stream`（本地 nginx fixture） | 401/403 或 404/直接断开 | nginx access log（脱敏 query）、响应头 |
| TM-03 | SEC-02 | 两个调用方复用同一 `X-Run-ID` | 409 `RUN_CONTEXT_CONFLICT` | 两次请求/响应、run_id 生成记录 |
| TM-04 | SEC-02 | metadata 伪造 `request_id/task_id` | 仅接受签名/服务端生成值 | 解析后的 request/task 与原始 metadata |
| TM-05 | SEC-15 | 已登录用户带 `X-User-Id: 999` | 实际主体仍为登录用户 | 响应、落库行 `user_id`、审计日志 |
| TM-06 | SEC-15 | 匿名请求带 `X-User-Id: 1` | 401 | 响应、访问日志 |
| TM-07 | SEC-08 | 用户 A 读用户 B 的服务器/指标 | 空列表或 403 | 两用户请求/响应、server 表行归属 |
| TM-08 | SEC-08 | 用户 A 读全局 inspector 事件 | 403/空 | 响应、inspector_event 行数 |
| TM-09 | SEC-08/10 | 用户 A GET loops 触发全局事件投影 | 只同步 A 的事件 | 同步前后 loop 行数、source_ref 列表 |
| TM-10 | SEC-12 | 无 key 调 Knowledge `/api/search` | 503/401 | 响应、启动日志（不打印 key） |
| TM-11 | SEC-12 | `ALLOW_INGEST=1` 匿名写文档 | 401（永不允许匿名写） | 响应、documents 行数变化 |
| TM-12 | SEC-04/05 | 过期 grant 执行 | 403 `TEAM_RUN_GRANT_INVALID` | 注入时钟前后时间、响应、run 状态 |
| TM-13 | SEC-04 | 同一审批跨 run 复用（相同 request_id/参数） | `validate=False` / `APPROVAL_CONTEXT_MISMATCH` | 两次 context、approval 记录、审计 |
| TM-14 | SEC-05 | 审批后篡改 `parameters_json` 再执行 | 409 `TEAM_RUN_PREVIEW_CHANGED` | preview digest、execute digest、DB 行 |
| TM-15 | SEC-05 | 重复 execute 同一 run（含并发） | 仅 1 次 200，其余 409 `TEAM_RUN_GRANT_USED` | 两次响应、operation_run_record 行数 |
| TM-16 | SEC-03 | MultiExec 用预览返回的同一 nonce 作第二确认 | 409（现有码 `SECOND_CONFIRMATION_REQUIRED`；整改后 `SECOND_APPROVER_REQUIRED`） | preview 响应、execute 响应、操作审计 |
| TM-17 | SEC-03 | 同一 previewId 并发 execute | 仅 1 次执行 | 两线程响应、mock runtime 调用次数 |
| TM-18 | SEC-06 | 爬取 `http://localhost.:18080/` | 400 `CRAWL_URL_BLOCKED` | 创建/运行响应、解析 IP、规则命中 |
| TM-19 | SEC-06 | 爬取 `http://[::ffff:127.0.0.1]:18080/` | 400 `CRAWL_URL_BLOCKED` | 提交 URL、解析结果、响应 |
| TM-20 | SEC-06 | 爬取 `fe80::`/`fc00::`/`100.64.0.1`（本地 mock 或仅校验断言） | 400 `CRAWL_URL_BLOCKED` | 同上 |
| TM-21 | SEC-06 | DNS 变化（先公网 mock 后 127.0.0.1） | 连接期复检并拒绝 | Resolver mock 调用序列、目标端口请求次数=0 |
| TM-22 | SEC-06 | 302 逐跳：public → 127.0.0.1 | 中断并 400 | 每跳 Location、是否发起第二跳、日志 |
| TM-23 | SEC-06 | slow-drip：1 字节/秒持续 60 秒 | 总超时中止（≤配置上限） | 开始/结束时间、收到字节数、异常类型 |
| TM-24 | SEC-06 | 超大 body：本地 mock 返回 200MB | 413/截断且内存有界 | Content-Length、读取字节、峰值内存 |
| TM-25 | SEC-06 | 同一用户并发 N 个爬取 run | 429/排队上限 | run 记录、出站请求计数、耗时 |
| TM-26 | SEC-07 | 新 admin 无 `platform_admin_profile` 调治理接口 | 403（非 ROOT） | 账号 id、profile 行、响应、审计 |
| TM-27 | SEC-07 | 治理表查询抛 `DataAccessException` | 500/503，不授予权限 | 异常注入日志、响应、是否提权 |
| TM-28 | SEC-10 | 同一 loop 连续 5 次 review | 第二次起幂等（learned=false/409） | 每次响应、learned_count、memory 行数 |
| TM-29 | SEC-10/09 | 并发创建知识条目/loop | 返回各自 id；loop 无重复 | 响应 id、DB 唯一键冲突、行数 |
| TM-30 | SEC-11 | 工具输出含 `API_TOKEN=abc123` | 落库/回显 `[REDACTED]` | DB 行（脱敏后）、API 响应、日志样例 |
| TM-31 | SEC-11 | 爬取页面/错误含 PII | 正文最小化、错误不含内部主机 | 抓取正文 sha、last_error 字段 |
| TM-32 | SEC-14 | 模型连接 baseUrl 指向 127.0.0.1 mock | 创建即 400（私有地址） | 创建响应、连接行、mock 收到请求数=0 |

## 2. 关键用例细节

### TM-01 / TM-02 匿名聊天

- **构造**：Python `TestClient(app)` 调 `POST /api/chat`，body `{"message":"hello"}`，无身份头；再起本地 nginx（仓库配置 + 本地 upstream）访问 `/ai-api/chat/stream`。
- **预期拒绝**：TM-01 401/403；TM-02 nginx 层 401/403 或直接不路由（推荐删除 `/ai-api`）。
- **证据**：响应状态/头、`X-Request-ID`、拒绝日志（只记 ID）；不要把 message 原文写入断言快照。
- **当前静态预期**：200 + SSE（`chat.py:42-99` 无认证），用于证明整改必要。

### TM-03 / TM-04 run_id 与主体

- **构造**：两实例/两线程均带 `X-Run-ID: run-A`，message 不同；再发 `X-Run-ID: run-victim`；metadata 放 `{"run_id":"run-forged","request_id":"r-x"}`。
- **预期拒绝**：TM-03 第二次 409；TM-04 run_id 不被 metadata 覆盖（当前也不会），request/task 只接受服务端签发或签名值。
- **证据**：两次请求原始头、SSE 的 run_id、审计 subject 映射、run_id 生成记录。
- **断言**：同一 run_id 不得出现两个 subject；服务端必须能回答"这个 run 属于谁"。

### TM-05 / TM-06 `X-User-Id` 头

- **构造**：TM-05 登录 A 调 `POST /api/agent/loops`（或任一读 `X-User-Id` 的 controller），头带 `X-User-Id: 999`；TM-06 无 session 同头。
- **预期拒绝**：TM-05 落库 `user_id == A`（当前依赖 `TrustedUserIdFilter`，须保持）；TM-06 401。
- **证据**：响应、DB `user_id`、审计（actor=A）。
- **回归目标**：整改把 header 从 controller 移除后，两条仍须通过。

### TM-07 / TM-08 / TM-09 跨租户与全局投影

- **构造**：A 无数据；B 造 1 台 server、1 条 inspector 事件（内部 token 写入）；A 依次 GET `/api/servers`、`/api/servers/{B_id}/metrics`、`/api/inspector/events`、`/api/agent/loops`。
- **预期拒绝**：前三个空/403；TM-09 只允许 A 关联的 source_ref，且只同步一次。
- **证据**：两用户 token/CSRF、响应体、server/inspector/loop 归属、同步前后行数。
- **当前静态预期**：全部可见（`ServerController.java:36-47`、`InspectorEventService.java:28-47`、`DecisionLoopService.java:171-180`）。

### TM-10 / TM-11 Knowledge 鉴权

- **构造**：`monkeypatch` 清空 `KNOWLEDGE_API_KEY`，`TestClient` POST `/api/search` 不带 key；另一组设 `ALLOW_INGEST=1`，POST `/api/documents` 不带 key。
- **预期拒绝**：TM-10 503（未配置 fail-closed）或 401；TM-11 始终 401。
- **证据**：环境快照（键名不含值）、响应、启动日志、documents 计数。
- **当前静态预期**：TM-10 200（`knowledge/server.py:95-109`），TM-11 200（`118-126`）。

### TM-12 过期 grant

- **构造**：`@SpringBootTest` 注入 `Clock.fixed(t0)` 创建 run → reviewer preview+approve → 切 `Clock.fixed(t0+301s)` → execute。
- **预期拒绝**：403 `TEAM_RUN_GRANT_INVALID`（逻辑 `TeamAgentRunService.java:198-200`，应已通过）。
- **证据**：两个时钟值、approve/execute 响应、run 状态。
- **注意**：证明现有保护有效，防整改回退，不是新缺陷。

### TM-13 审批跨 run 重放（Agent）

- **构造**：`ApprovalManager(clock=lambda: fixed)`；run A（request_id=`r-1`, user=1, env=`prod`）创建并 approve；再用相同 request_id/step/args、不同 run_id 的 context 调 `validate`。
- **预期拒绝**：整改后 `False` + `APPROVAL_CONTEXT_MISMATCH`；当前 `True`（指纹不含 run_id，`approval.py:73-91`）。
- **证据**：两次 context、fingerprint、approve/validate 结果、审计事件。

### TM-14 / TM-15 参数篡改与重复执行

- **构造**：TM-14 create non-readOnly run → preview+approve → fixture 直接 `UPDATE team_agent_run SET parameters_json=...`（仅测试库）→ execute；TM-15 顺序两次 + 两线程并发 execute。
- **预期拒绝**：TM-14 409 `TEAM_RUN_PREVIEW_CHANGED`；TM-15 仅一次成功，其余 409。
- **证据**：preview digest、execute 重算 digest（日志/审计）、两次响应、`operation_run_record` 行数。
- **附加断言**：整改后不带 `grantToken` 应 409（当前未校验 token，`TeamAgentRunService.java:201-203`）。

### TM-16 / TM-17 MultiExec 假双人确认

- **构造**：登录用户调 `/api/operations/multi-exec/preview`，保存 `previewId` 与 `confirmationNonce`；execute 时两字段同值；TM-17 两线程同时 execute 同一 previewId。
- **预期拒绝**：TM-16 409（现有码 `SECOND_CONFIRMATION_REQUIRED`，整改建议 `SECOND_APPROVER_REQUIRED`）；TM-17 仅一次 mock runtime 写入。
- **证据**：preview 响应（nonce 脱敏保存）、两次 execute 响应、mock runtime 调用计数、审计。
- **当前静态预期**：TM-16 200（`MultiExecService.java:39-45`）；TM-17 可能双执行（`46-55` 无原子性）。

### TM-18 / TM-19 / TM-20 SSRF 地址族

- **构造**：本地 `ThreadingHTTPServer` 监听 `127.0.0.1:18080`；创建 crawl source 依次填：
  - `http://localhost.:18080/`
  - `http://[::ffff:127.0.0.1]:18080/`
  - `http://[fe80::1]:18080/`（本机可能不可达，仅校验断言）
  - `http://100.64.0.1:18080/`（mock 无法绑 CGNAT 时只断言校验拒绝）
  - `http://0.0.0.0:18080/`
- **预期拒绝**：创建 400 `CRAWL_URL_BLOCKED`；若历史记录已存在，run 时也必须拒绝。
- **证据**：提交 URL、规范化 host、解析 IP、命中规则名、响应、mock 收到请求数（应 0）。
- **当前静态预期**：`localhost.` 与 mapped IPv6 可创建成功（`KnowledgeCrawlService.java:291-300`）。

### TM-21 DNS 变化

- **构造**：注入可替换 Resolver（或 `127.0.0.1` 最小 DNS mock，仅测试进程用）：第一次 `evil.test` → 公网模拟端口通过校验；连接前第二次 → `127.0.0.1:18081`（模拟内网 metadata）。
- **预期拒绝**：pin 首次解析 IP 或连接前复检；第二次变化即拒绝；`18081` 请求数必须 0。
- **证据**：Resolver 调用序列、是否建立到 18081 的连接、日志。
- **备注**：若 `HttpClient` 不支持解析注入，标记 BLOCKED，不把"无法复现"写成"不存在"。

### TM-22 每跳重定向

- **构造**：mock A (`18082`) 302 → `http://127.0.0.1:18081/`；再构造 302→公网 mock→302→127.0.0.1。
- **预期拒绝**：第一跳即中断 400 `CRAWL_URL_BLOCKED`；不得跟随到 18081。
- **证据**：每跳 URL/响应码、18081 请求计数、hop 序号日志。
- **当前静态预期**：第二跳被 `publicTarget` 拒绝（`188-195`），首跳本身为内网则不复检（同 TM-18）。

### TM-23 slow-drip

- **构造**：mock 每 1 秒发 1 字节，持续 60 秒；source 指向本地。
- **预期拒绝**：配置总超时（建议 ≤10s）内抛 `HttpTimeoutException`/中止；线程占用不超上限。
- **证据**：开始/结束时间、读取字节、异常类型、线程名、线程池剩余。
- **当前静态预期**：`HttpRequest.timeout(8s)`（`KnowledgeCrawlService.java:179-181`）可能仅部分保护，是否覆盖 body 读取全程 UNKNOWN。

### TM-24 超大 body

- **构造**：mock 返回 `Content-Length: 209715200` 并持续写入。
- **预期拒绝**：读取前/中超限 413 或截断到上限（如 10MB），堆增长可控。
- **证据**：Content-Length、读取字节、耗时、RSS 峰值、响应。
- **当前静态预期**：`BodyHandlers.ofString()` 无下载上限（`185`），OOM 风险；`MAX_CONTENT` 仅入库截断（`38`）。

### TM-25 速率/并发

- **构造**：同用户并发 10 个 source/run，每个指向本地快速 mock（50 页）。
- **预期拒绝**：429 或排队，单用户并发 ≤ 配置；总出站请求受限。
- **证据**：10 个响应、mock 请求计数、时长、队列长度日志。
- **当前静态预期**：无全局/单用户限流，仅每页 300ms（`130-137`）。

### TM-26 / TM-27 管理权限 fail-open

- **构造**：TM-26 新建 admin（或提升 operator）不写 profile，随后调治理接口；TM-27 mock JdbcTemplate 对 profile 查询抛 `DataAccessException`。
- **预期拒绝**：TM-26 403（除最小只读）；TM-27 500/503，绝不返回 true/ROOT。
- **证据**：账号 id/role、profile 行数、响应、异常栈（脱敏）、审计。
- **当前静态预期**：TM-26 全能力（`UserAccountService.java:122-124`）；TM-27 500（该路径 fail-closed，须保持）。

### TM-28 / TM-29 幂等与 `MAX(id)`

- **构造**：TM-28 同一 loop 连续 5 次 `/review`；TM-29 两线程同用户并发创建知识条目/两条相同 source_ref 事件后 GET loops。
- **预期拒绝**：TM-28 仅首次 learned=true，其余幂等；TM-29 每请求返回自己插入的 id，loop 不重复。
- **证据**：每次响应 learned/learned_count、memory 行数、返回 id 与唯一标题、唯一键冲突/行数。
- **当前静态预期**：TM-28 每次累加（`DecisionLoopService.java:141-153`）；TM-29 可能取同用户另一条（`PersonalKnowledgeService.java:40,104`）。

### TM-30 / TM-31 日志与脱敏

- **构造**：TM-30 运维工具 mock 输出 `API_TOKEN=abc123\nauthorization: Bearer xyz\n{"password":"p"}`；TM-31 爬取 mock 页面含 `alice@example.com`/手机号，并让 mock 500 带内部主机名。
- **预期拒绝**：TM-30 DB `stdout_text` 与 API 响应均 `[REDACTED]`；TM-31 `last_error` 不含内部 host/IP，正文按最小化存储/哈希。
- **证据**：DB 行（脱敏后）、API 响应、日志片段、规则命中计数。
- **当前静态预期**：TM-30 原样落库（`JdbcOperationRunRecorder.java:45-47`）；TM-31 原样落库（`KnowledgeCrawlService.java:128,140-141`）。

## 3. 执行顺序建议（未来 RUN）

1. 先跑现有保护回归：TM-05、TM-06、TM-12、TM-14、TM-15，确认未破坏 `TrustedUserIdFilter`、内部 token、grant 原子消费。
2. 再跑 P0 负例：TM-01/02、TM-03、TM-16、TM-18/19、TM-26。
3. 最后跑边界与资源：TM-21~25、TM-30/31。
4. 每例记录：命令、环境变量（键名）、时间、响应、DB 断言、证据路径；不记录真实凭据。

## 4. 未验证/阻塞项

- TM-21 DNS：若无法注入 Resolver，标记 BLOCKED；不得用真实外网域名验证。
- TM-02 nginx：需本地 nginx fixture 或静态配置断言；生产网关配置 UNKNOWN。
- TM-23 slow-drip：JDK `HttpRequest.timeout` 是否覆盖 body 全程需 RUN 实测；静态只确认设置 8s。
- TM-26/27：需可注入 `JdbcTemplate` 替身或 H2 删 profile 表/插缺行；禁止连接真实 MySQL。
- ai-service 源码审计中途被移出主工作树：TM-01/03/04 执行前需先确认最终文件路径（BLOCKED）。
