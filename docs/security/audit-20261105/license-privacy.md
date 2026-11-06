# HC-02 数据 / 日志 / 许可边界与脱敏白名单

- 日期：2026-11-05
- 性质：静态审计结论 + 整改约束；未读取真实用户数据，未连接数据库。
- 适用：SmartOpsAgent 仓库（Java 后端、Vue 前端、ai-service、agent、knowledge）、部署配置、CI、参考语料。
- 结论：**代码仓库本身 MIT；参考语料缺少逐文件来源/许可元数据，其再分发与商用属 UNKNOWN/BLOCKED；运行期敏感数据面（工具输出、爬取正文、巡检证据）缺统一分级与脱敏，必须先立"不得入日志"清单再整改。**

## 1. 代码与依赖许可

### 1.1 仓库许可

- `LICENSE:1-3`：MIT License，Copyright (c) 2026 SmartOpsAgent contributors。
- 结论：自有代码可按 MIT 使用/修改/再分发，需保留版权与许可声明。
- 约束：新增文件不得引入与 MIT 不兼容的代码片段；复制第三方实现需在文件头注明来源与许可。

### 1.2 第三方依赖

- 基线（复用 `docs/audit/20261105/status-baseline.md` 的 GH-P0-01）：46 个依赖坐标已锁定，但"官方仓库 commit 核验"为 `NOT_RUN`；本次不重复求证。
- 风险：仓库内未见 SBOM/NOTICE；`.github/workflows/ci.yml:1-100` 只有 lint、`mvn test`、`pytest`，未见依赖漏洞扫描、许可证扫描、secret scan。
- 要求：发布前生成第三方 NOTICE（至少直接依赖），GPL/AGPL/SSPL 类人工评审；不得把"未核验"写成"已合规"。
- 归属：HC-05（发布/供应链）；HC-02 只登记。

### 1.3 参考语料许可（BLOCKED）

- `knowledge/corpus_manifest.py:40-44`：manifest 仅含 `path/sha256/bytes`，**无 license/source URL/attribution 字段**。
- `knowledge/reference/ops-knowledge-rag/云原生公开课_分章md/08.参考资料与致谢.md:5-11`：来源为非正式列举（厂商方案、白皮书、公众号、搜索引擎），无具体授权条款。
- `knowledge/server.py:153-174` 的 `_seed_reference_corpus` 只统计文档/哈希，不含许可；`256-258` 健康输出同样不含。
- 结论：该语料可"本地内部检索"的前提是已获授权；仓库内无授权证据，**对外分发、商用、公开演示整段引用均为 UNKNOWN/BLOCKED**。
- 整改（HC-04）：1) manifest 增 `license/source_url/retrieved_at/attribution`，缺失即校验失败；2) 无明确许可默认 `internal_only=true`，不进入对外 RAG 响应；3) 删除/替换无法追溯来源的段落，不只改文件名。

## 2. 数据分级

| 级别 | 定义 | 示例 | 存储 | 日志 | 外发 |
| --- | --- | --- | --- | --- | --- |
| L0 公开 | 无敏感性状态 | `/api/health` 的 status、版本号（不含内部 host） | 可 | 可（白名单字段） | 可 |
| L1 内部标识 | 关联 ID、计数、耗时、状态码 | request_id/run_id/task_id/trace_id/duration/status | 可（按保留期） | 可（allowlist 正则） | 不外发 |
| L2 业务内容 | 用户输入/抓取正文/工具输出/巡检证据 | message、图片、crawl markdown、stdout/stderr、evidence、tool args | 加密/最小化，按保留期 | **默认禁止**（仅脱敏摘要/哈希） | 默认不外发；模型调用除外（§5） |
| L3 凭据与密钥 | 口令、token、私钥、连接串、Cookie | `X-Admin-Password`、Authorization、`X-API-Key`、DB 密码、SSH 私钥、credential 明文 | 加密（KMS/外部密钥），最小权限 | **绝对禁止** | 绝对禁止 |

补充：

- L3 密文也不得进日志；只记录 `credential_id` 与 `last4`（`V20261002__operations_and_accounts.sql:9`）。
- L2 跨用户可见性必须与 scope 一致（SEC-08）；日志脱敏不能替代访问控制。
- 临时排障打印 L2/L3 必须本地开关且默认关，合并前移除。

## 3. 日志白名单（允许写入）

只允许以下结构化字段（值经 allowlist 正则或枚举校验）：

1. `request_id/task_id/run_id/trace_id/conversation_id`：满足 `[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}`（`agent/runtime_events.py:7-12`、`knowledge/server.py:82-88`）。
2. `status/status_code/error_code`：枚举值。
3. `duration_ms/count/page/page_size`：数值。
4. `route`：**路由模板**（如 `/api/agent/loops/{id}`），不记原始 URL query。
5. `provider/model`：模型供应商标识，不含 baseUrl/key。
6. `actor_user_id`：仅写安全审计库，应用日志建议哈希/内部短 ID；不得与 L2 同条。
7. `content_sha256`：L2 内容哈希，用于完整性，不可逆。

现有正向实现（整改须保留）：

- `agent/runtime_events.py:1`：明确"Payloads, credentials and prompts never enter here"。
- 审计时快照 `ai-service/app/services/chat.py:63-66`：聊天开始只记 request/task/run ID 与 mode。
- `knowledge/server.py:82-88`：相关性 ID 只回显 allowlist 值。
- `agent/safety/approval.py:31-35`：审批管理器定位 trusted-host/process-local，不反序列化客户端 grant。

## 4. 日志黑名单（不得入日志/审计摘要）

1. Prompt/message/system prompt/上传图片/OCR/对话历史。
2. 工具参数与输出原文（command_text、stdout_text、stderr_text、env、docker inspect、kubectl describe）。
3. 巡检 evidence 原文、RAG 召回片段、知识条目正文。
4. 爬取页面正文/HTML/Cookie/请求响应头。
5. 任何 Authorization、Cookie、Set-Cookie、X-API-Key、X-Admin-Password、X-CSRF-Token。
6. DB 连接串/账号/口令、Redis 口令、SSH 私钥/口令、credential 明文或密文。
7. 模型 API key、网关 key、内部 token。
8. 原始 URL query（可能含 token）；只记 `scheme+host+path_template` 或哈希。
9. 用户 PII：邮箱、手机号、身份证、地址、聊天附件、爬取页面个人信息。
10. 完整异常对象（可能含请求体）；只记类名+错误码+关联 ID，堆栈仅本地调试。

`deploy/nginx/nginx.conf:68-79` access log 记录完整 request line；token 放 query 会落盘。整改要求 token 不进 query，并在 nginx 层裁剪 query 或关闭敏感路径 access log。

## 5. 外发与第三方共享

- 聊天把 message 与 RAG 片段发给模型供应商，属 L2 外发：1) UI/隐私说明披露；2) 供应商选择与保留策略 HC-05 审核；3) 禁止把 L3 拼进 Prompt。
- 模型连接 baseUrl 可由任意登录用户配置（`ModelConnectionService.java:322-339`、`ModelProviderClient.java:85-96`），L2 可能发往用户指定地址；整改前限制为管理员 allowlist 供应商（SEC-14）。
- 爬取内容来自第三方：需遵守站点条款与 robots（代码未见 robots 处理，**UNKNOWN**）；无授权内容默认 `internal_only`，不得对外展示原文。
- 检索结果可能含其他用户/团队 L2（SEC-08），外发前必须 scope 过滤。

## 6. 脱敏实现要求

### 6.1 现状与缺口

- `OperationRedactor.java:6-14` 仅匹配 `password|passwd|secret|token|api_key` 等 `key=value`，且只在 SSH/WS 调用（`SshConnectionAdapter.java:203-207`）。
- Java 工具执行 `OperationToolService.java:189-192` → `JdbcOperationRunRecorder.java:45-47` 原样落库；`OperationRunQueryService.java:54-57` 原样返回。
- 爬取错误/正文（`KnowledgeCrawlService.java:128,140-141,165-166`）、巡检 evidence（`InspectorEventService.java:114-119`）原样落库。

### 6.2 统一规则

1. **先分级再落库**：入口标记 L2/L3；L3 拒收，L2 最小化+脱敏。
2. **键名优先**：`password|passwd|pwd|secret|token|access_token|refresh_token|api_key|apikey|authorization|cookie|set-cookie|private_key|client_secret|session` 不区分大小写。
3. **值形态**：`Bearer`、`Basic`、`BEGIN PRIVATE KEY`、URL `user:pass@`、JDBC `;password=`。
4. **结构化**：JSON/query/header 敏感键替换 `[REDACTED]`，保留键名便于排障。
5. **不可脱敏字段**：二进制/大文本宁可不存，只存 `sha256` 与长度。
6. **二次兜底**：写库前 + 读出前，均有单测（TM-30）。
7. **审计例外**：审批 digest、参数哈希可存；原始参数不得存明文日志。

### 6.3 脱敏白名单（可保留）

- 运行标识：run_id/request_id/task_id/trace_id（session_id 建议哈希）。
- 执行元数据：tool_id/tool_version/runtime_id/exit_code/duration_ms/sequence_no。
- 审批元数据：approval_id/approver_id(内部)/decision/expires_at/digest。
- 网络元数据：scheme/host(内部域名可保留)/status_code/bytes_read/redirect_count；query 剔除。
- 完整性：sha256/bytes。

**不在白名单即不得写入**；新增字段 PR 说明分级与保留期。

## 7. 保留期与删除

- 现状：`operation_run_output`、`operation_run_evidence`、`inspector_evidence`、knowledge 条目的保留/删除未见统一实现（**UNKNOWN**）。
- 建议基线（HC-01/HC-05 确认）：1) L2 工具输出默认 30 天，超期归档/删除，用户可删 run；2) 巡检 evidence 90 天，随事件级联删除（外键 `ON DELETE CASCADE`，`V20261002__operations_and_accounts.sql:4-6`）；3) 知识条目用户删除即物理删除；4) 应用日志 14 天，安全审计 180 天（仅 L1）；5) 备份同权限，删除请求覆盖备份（流程要求）。
- 禁止以"分析需要"无限期保留 L2 原文而不告知用户。

## 8. 许可/隐私验收清单（未来 RUN）

- [ ] LICENSE 保留；新增第三方代码有来源/许可注释。
- [ ] 生成并提交第三方 NOTICE/SBOM（HC-05）。
- [ ] 参考语料 manifest 含 license/source_url/attribution；无许可文档 internal-only。
- [ ] 聊天/爬取/巡检/工具输出落库前经统一 redactor（TM-30/31）。
- [ ] 日志样例扫描无 Prompt/凭据/PII（白名单外为零）。
- [ ] nginx access log 不含 query token；`X-Admin-Password` 不进日志。
- [ ] 模型外发有披露与供应商清单；模型连接限管理员配置。
- [ ] 保留期与删除策略经 HC-01/HC-05 确认。

## 9. 仍为 UNKNOWN / BLOCKED

- 参考语料实际授权状态：仓库内无证据，**BLOCKED**，不得对外分发。
- 生产模型供应商数据保留/训练条款：无配置，UNKNOWN。
- 爬取是否遵守 robots.txt/站点条款：代码未见处理，UNKNOWN。
- 历史 L2 数据实际保留时长与备份位置：UNKNOWN。
- 生产日志采集端（ELK/Loki）与访问权限：仓库只有 compose，UNKNOWN。
- `operation_credential` 生产密钥是否 KMS 注入：local 固定 key（`application-local.yml:61`），生产 UNKNOWN。
- ai-service 源码审计中途被移出主工作树：相关日志行号为审计快照，IMPLEMENT 前需复核（BLOCKED）。
