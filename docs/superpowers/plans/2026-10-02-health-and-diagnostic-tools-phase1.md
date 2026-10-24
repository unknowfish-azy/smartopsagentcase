# 健康诊断与实用工具第一阶段实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans after user review. Native implementation in the current workspace is proposed; do not create branches or commit.

**Goal:** 交付健康诊断中心、HTTPS 证书检查、HTTP/API 检查、浏览器本地配置差异检查。

**Architecture:** 复用现有会话、管理员门户、工具目录和主题变量。后端新增受目标授权保护的诊断服务，不将网络检查接入 SSH 任意命令链。配置差异在浏览器本地处理，新页面和面板按需加载。

**Tech Stack:** Java 17、Spring Boot 3.3.5、Vue 3、Vite、JUnit、Node test、Playwright。

**Spec:** 本文的设计与接口边界章节，细化用户已确认的第一阶段建议。

**Status:** 2026-10-02，功能方向已确认；以下具体边界待用户审核。尚未修改功能代码。

## 已核对的项目基础

- AdminReadinessController 返回关键表访问、观测源配置、Harbor 配置与内部认证配置摘要。
- AdminReadiness.vue 已区分已配置与真实连通性，明确不自动调用模型或连接 SSH。
- OperationToolController / OperationToolService 提供远程工具预览、执行和运行记录；新工具不冒充远程运行时工具。
- SecurityConfig 保护会话、管理员接口与 CSRF；SessionUser 同时包含角色和登录门户。
- 现有工具页为 /tools/:toolId；要为本地工具和服务探测增加独立执行类型。

## Global Constraints

- 本阶段不加入定时任务、告警通知、自动修复、扫描网段、任意命令和付费模型调用。
- 不改真实账号、密码和数据库数据；不提交、不建分支、不重置或清理已有脏改动。
- 使用 apply_patch 修改 UTF-8 文件；不通过 PowerShell 默认编码重写中文源码。
- 网络探测只接受授权 targetId；连接超时 3 秒、总耗时 10 秒、响应上限 256 KiB。
- 每用户并发最多 2 次、全局最多 8 次；异常时释放额度，超限返回明确错误。
- 配置差异每侧最多 256 KiB、5000 行；原文不上传、不交给 AI、不持久化。
- 使用现有语义主题变量和异步路由，不提高 chunkSizeWarningLimit。

## 设计与接口边界

### 健康诊断

普通用户查看自己有权访问的资源摘要；管理员角色且管理员门户才能读取全局数据库、关键表和依赖配置。
统一结果字段：id、label、status、scope、checkKind、checkedAt、durationMs、summary、nextAction。
状态固定为 HEALTHY / UNHEALTHY / UNCONFIGURED / FORBIDDEN / NOT_CHECKED。
检查类型为 CONFIGURATION / LOCAL_CHECK / ACTIVE_PROBE；配置存在不能推断业务可用。

- 浏览器/后端：记录真实请求证据与耗时，只证明本次访问，不承诺所有业务正常。
- 数据库：先做限时连接检查；失败时关键表显示未检查，不将全部表判为缺失。
- 关键表：沿用已有清单，读取失败显示不可访问，不擅自断言表不存在。
- Mini：只做不调用外部模型的本地能力检查；未实际运行时显示配置/加载状态。
- 外部模型、Harbor、监控源：默认配置摘要，主动检查走明确授权入口。首版不能验证的项目显示未检查及操作入口。
- SSH：保留连接中心入口，不自动登录主机和执行远程命令。
- 检查失败时保留的旧结果必须标注过期，不能继续作为当前正常状态展示。

接口：GET /api/diagnostics/health 为当前用户摘要；GET /api/admin/diagnostics/health 为管理员检查。
保留现有 /api/admin/readiness 契约，避免破坏既有调用与测试。

### 网络工具共同边界

首版由管理员维护服务端配置白名单；不提供任意 URL 输入或目标管理 CRUD 页面。
目标包含 targetId、displayName、scheme、hostname、port、path、pinnedAddresses、allowedUserIds、expectedStatus。
普通用户授权列表为空默认拒绝。每次执行重新检查权限，不能依赖前端筛选。
浏览器只提交 targetId 和受限断言，不提交 userId、IP、认证头或任意请求头。

- 仅 HTTP/HTTPS，默认端口 80/443；其他端口需管理员逐项配置。
- 出站连接固定到批准的地址，TLS SNI 与主机名验证仍使用配置域名；不采用校验 DNS 后再次解析的传输模式。
- 未批准的地址拒绝。私网目标须精确批准；回环、链路本地、元数据、组播和未指定地址禁止作为业务目标。
- 首版不跟随重定向；只展示脱敏后的跳转提示，避免跳转到未授权地址。
- 不继承环境代理、Cookie 或系统登录凭据，不支持自定义 Authorization/Cookie 头。
- 仅读取有上限的响应，压缩解码后同样限额，不回传完整正文、凭据或异常堆栈。
- 审计仅记操作者、目标 ID、工具、时间、状态、耗时，不记录敏感响应。
- 白名单为空时展示未配置，不自动配置演示或生产目标。

接口：GET /api/diagnostics/targets；POST /api/diagnostics/http；POST /api/diagnostics/certificate。
复用 ApiResponse 与真实 SessionUser；POST 遵守现有 CSRF 机制。

### HTTPS 证书工具

返回证书颁发者、适用域名、有效期、剩余天数、主机名与信任链验证状态、检查时间及耗时。
30 天预警、7 天紧急；过期、主机名不匹配、链不受信任分开显示。
不关闭 TLS 验证，不自动续签或替换证书；握手失败且无法安全取证时，日期等字段显示未知。
不把基础证书检查描述为完整 TLS 安全审计或吊销状态验证。

### HTTP/API 工具

首版只支持 GET/HEAD；请求可能产生目标访问日志或服务端副作用，不承诺零副作用。
展示状态码、总耗时、读取大小、截断标记、断言结果与安全错误分类。
网络请求成功与业务断言通过分开展示；总耗时不冒充 DNS/TCP/TLS 独立耗时。
JSON 断言仅支持点分对象字段、存在性与标量相等，不执行脚本、任意正则和表达式。
HEAD 禁止正文断言；大响应未完成正文读取时显示无法判断，不判定通过。

### 配置差异工具

左右粘贴或选择本地文本文件；显示新增、删除、变更和未变更行，支持清空与脱敏结果下载。
首版为有计算量上限的文本行差异；JSON/YAML/INI/ENV 作为文本处理，不宣称语义校验。
默认保留空白含义，可选忽略行尾空白；超限明确提示，不无限分配内存或阻塞 UI。
预览与下载默认隐藏常见 password、secret、token、api_key、Authorization 和私钥块。
脱敏不等于完整 DLP 保证，提示人工复核；秘密值变化仍保留该行已变化标记。
以文本节点渲染，不使用 v-html；离开工具、退出或切换账号时清除内存原文。

### 前端入口与体验

新增 /health；保留 /admin/readiness，复用共享显示组件但由后端授权数据范围。
工具中心增加服务诊断分组；执行类型区分 remote-runtime / service-probe / local-browser。
浅色、深色、跟随系统实时同步，状态同时使用文字；键盘可操作、移动端无横向溢出。
请求期间显示忙碌状态，失败可重试；取消或忽略页面离开/账号切换后的旧请求。

## Review Focus

- 伪造 targetId、X-User-Id、角色时，在网络请求之前拒绝且不泄露其他用户资源。
- DNS 变化、重定向、IPv6 映射形式与非授权内网不能绕过出站限制。
- 超时、断开、压缩炸弹、超大响应、数据库不可用时，结果准确且请求有资源上限。
- HTML 输入、私钥、多行敏感值、超长单行和大量不同文本不泄密、不执行、不阻塞页面。
- 切换账号、离开页面、切换主题时，旧结果不污染新会话，两种主题信息均可读。

## Task 1: 目标授权与执行限额

Create backend/src/main/java/com/smartops/diagnostics/DiagnosticTargetProperties.java、DiagnosticTargetPolicy.java、DiagnosticProbeLimiter.java。
Create backend/src/test/java/com/smartops/diagnostics/DiagnosticTargetPolicyTest.java、DiagnosticProbeLimiterTest.java。
Modify backend/src/main/resources/application.yml 与 .env.example，仅加入默认拒绝的配置示例。

- [ ] 先写默认拒绝、跨用户、管理员门户、协议/端口/地址绕过和并发测试，运行确认失败。
- [ ] 实现管理员白名单、脱敏目标列表、每次执行授权、限额及 finally 释放。
- [ ] 验证未授权目标不创建连接，异常后可继续使用额度。

## Task 2: HTTP 与 TLS 服务

Create diagnostics/DiagnosticTransport.java、HttpProbeService.java、CertificateProbeService.java、DiagnosticResult.java。
Create backend/src/main/java/com/smartops/controller/DiagnosticToolController.java。
Create diagnostics/HttpProbeServiceTest.java、CertificateProbeServiceTest.java 与 integration/DiagnosticToolSecurityIntegrationTest.java，位于 backend/src/test/java/com/smartops/。

- [ ] 使用隔离本地网络 fixture 编写状态码、断言、HEAD、超时、重定向、正文上限与 TLS 失败测试，先运行失败。
- [ ] 实现固定批准地址且保留 SNI/主机名校验的传输，不使用绕过证书验证的捷径。
- [ ] 实现安全错误分类、受限 JSON 断言和仅元数据审计。
- [ ] 用实际安全过滤链测试匿名、CSRF、跨账号、停用账号、强制改密与管理员用户门户，不只使用 standalone MockMvc。

## Task 3: 健康结果与权限隔离

Create diagnostics/HealthDiagnosticService.java 与 controller/HealthDiagnosticController.java。
Create diagnostics/HealthDiagnosticServiceTest.java 与 integration/HealthDiagnosticSecurityIntegrationTest.java。
必要时小范围修改 config/BusinessSchemaHealthIndicator.java，保持 AdminReadinessController 契约。

- [ ] 先测已配置但未检查、数据库不可用、表不可访问、未配置和无权限。
- [ ] 实现各项独立结果、连接/查询超时、一项失败不吞掉全部结果。
- [ ] 复用已存在的配置读取，不偷偷调用外部模型、SSH 或生产服务。
- [ ] 验证普通用户结果不包含表名、全局凭据状态或他人目标。

## Task 4: 本地配置差异引擎

Create frontend/src/domain/diagnostics/configDiff.js、redactConfig.js 与 frontend/test/config-diff.test.mjs。

- [ ] 先写空/相同/增删改、CRLF、中文、emoji、空白选项和稳定输出测试。
- [ ] 补字节/行数/计算量、长行、HTML、私钥与秘密值变化测试，运行确认失败。
- [ ] 实现有上限的行差异，禁止无限二次方分配；保留变更标记并脱敏显示和导出。
- [ ] 验证不访问网络、AI 客户端、localStorage 或其他持久化。

## Task 5: 页面与工具入口

Create frontend/src/api/diagnostics.js。
Create frontend/src/components/diagnostics/HealthCheckList.vue、NetworkDiagnosticTool.vue、ConfigDiffTool.vue。
Create frontend/src/views/diagnostics/HealthCenterView.vue 与 frontend/test/diagnostic-tools.test.mjs。
Modify frontend/src/views/operations/ToolsView.vue、toolCatalog.js，frontend/src/router/index.js，frontend/src/navigation/routeMetadata.js、personalSystemNavigation.js，frontend/src/views/admin/AdminReadinessView.vue。

- [ ] 先测工具执行类型、API 参数、空白名单、异步路由与权限，不改变既有工具 ID/远程执行契约。
- [ ] 实现选择目标、表单验证、检查中、失败重试、证据结果与过期提示。
- [ ] 实现纯本地文件输入、脱敏预览下载与清空；账号切换/卸载清除原文。
- [ ] 实现健康中心和管理员视图，服务端而不是前端承担权限隔离。
- [ ] 使用主题变量、可访问焦点和移动端布局，不新增无关全局样式覆盖。

## Task 6: 验收与操作文档

Create frontend/test/diagnostic-tools.browser.mjs 与 docs/operations/health-and-diagnostic-tools.md。
按需扩展 frontend/test/build-optimization.test.mjs，断言新模块隔离。

- [ ] 用隔离 fixture 验证实际请求、失败分类、超限、未授权零连接。
- [ ] 浏览器验证浅深主题实时切换、桌面/移动布局、安全文本显示和账号切换清理。
- [ ] 验证原始配置文本不上传、不持久化，普通页面仍不加载 Three.js。
- [ ] frontend 目录执行 npm.cmd test、npm.cmd run build 及新浏览器脚本。
- [ ] backend 目录使用 .mvn/smartops-settings.xml 执行新增和受影响 JUnit 测试；条件允许再扩大全量。
- [ ] 对本轮触及文件执行 git diff --check，审阅无关改动、中文编码和敏感数据。
- [ ] 记录白名单配置、能力限制和验收命令；未配置服务明确标注未验证。
- [ ] 旧 visual-check.mjs 选择器失效与已有 Three.js 警告单独报告，不假称本阶段已修复。

## Proposed Execution

建议在用户审核后由当前助手按任务顺序原生实施，保持当前已有工作区改动。
不添加大型新基础设施；若安全传输确需依赖，先明确其用途、版本与构建影响。
首版没有任意 URL 探测、带认证 API 探测、白名单管理页面或持久诊断历史；这些属于明确后续范围，不作为隐藏待办交付。
