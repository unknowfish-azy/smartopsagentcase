# SmartOpsAgent 全面体检与大模型任务总清单

> 版本：v1.0
>
> 编制日期：2026-11-05
>
> 适用项目：`D:/SmartOpsAgent`
>
> 用途：把项目当前状态、已有证据、剩余缺口和后续大模型任务统一整理成一份可分派、可验收、可回滚的总任务书。
>
> 本文件是规划和任务分派文档，不代表文中所有能力已经实现。本文件本身不要求新增业务代码。

---

## 0. 使用说明

这份清单解决四个问题：

1. 项目当前到底已经有什么。
2. 哪些能力只是设计完成，哪些已经有代码，哪些真正验证过。
3. 后续每个大模型应该接什么任务，不能同时碰哪些边界。
4. 每个任务做到什么程度才能写成“完成”。

所有任务都必须区分三个状态：

```text
design_status        设计状态
implementation_status 实现状态
verification_status   验证状态
```

统一状态词：

| 状态 | 含义 |
| --- | --- |
| `DONE` | 当前阶段有完整原始证据，可以复核 |
| `PARTIAL` | 已有部分实现或部分验证，不能宣称完整 |
| `IN_PROGRESS` | 正在实施或已有中间产物 |
| `NOT_STARTED` | 尚未开始 |
| `NOT_RUN` | 已有方案或代码，但本轮没有运行验证 |
| `BLOCKED` | 被环境、账号、许可、人工审核或前置任务阻塞 |
| `MOCK` | 仅替身、模拟、fixture 或本地 loopback |
| `HISTORICAL` | 历史记录中的结果，尚未在当前工作区重新核验 |
| `UNKNOWN` | 现有材料不足以得出结论 |

### 0.1 任何大模型接单前必须做的事

- [ ] 阅读根目录 `AGENTS.md`。
- [ ] 阅读 `README.md`。
- [ ] 阅读本文件及对应领域的已有任务书。
- [ ] 执行 `git status --short`，记录工作区现状。
- [ ] 记录当前 `git rev-parse HEAD`、运行环境版本和配置摘要。
- [ ] 查找同一领域已有代码、文档、测试和迁移，避免创建第二套实现。
- [ ] 给任务建立唯一 `task_id` 和独占写入目录。
- [ ] 写明本任务不修改的文件和边界。
- [ ] 先报告 `PLAN`，取得实施授权后才能进入 `IMPLEMENT`。

### 0.2 每项任务必须交付的四件东西

1. 改后方案或实现文件。
2. 改动前后的精确差分，以及文件所有权说明。
3. 原始验证命令、环境摘要、退出码和失败/跳过原因。
4. 哈希保护的回滚脚本，并在隔离副本中演练。

设计任务也必须交四件东西：第一项是设计文档，第二项是文档差分，第三项是 Markdown/链接/结构检查记录，第四项是文档回滚脚本。

### 0.3 绝对禁止事项

- [ ] 不执行 `git reset --hard`、`git clean`、整仓库回滚或覆盖其他模型的改动。
- [ ] 不因测试数量多就把功能写成完成。
- [ ] 不把 HTTP 200、端口可连、退出码 0、审批通过、模型回答“已完成”当作业务恢复。
- [ ] 不把 fixture、mock、历史日志或 README 自报能力当作真实生产证据。
- [ ] 不为了刷绿修改 Golden、测试期望、分母或删掉失败样本。
- [ ] 不在没有许可、PII、数据血缘和删除机制时导入外部数据集。
- [ ] 不在没有容量、隔离、迁移、退出和回滚证据时把 Qdrant、OTel、Phoenix、LangGraph 等新基础设施设为默认依赖。
- [ ] 不创建第二套用户、权限、审批、Run、审计或模型计费系统。
- [ ] 不把 `StateVerifier.passed`、检索分数、模型置信度、Inspector 结果和业务恢复混成一个字段。

---

## 1. 项目当前真实状态总览

### 1.1 已有产品能力

#### 用户层

- AI 对话、SSE 流式回答和思考阶段展示。
- 语音输入、图片证据、附件会话。
- 服务器基础管理和指标查看。
- SSH、SFTP、文件、命令、隧道、运行记录和执行证据。
- 个人知识库、团队知识、候选知识审核和版本感知检索。
- Agent 规划、风险策略、人工审批、受控执行和 Inspector 核验。
- Sentinel 任务、规则、脚本、告警和 Guardian 相关页面。
- 团队空间、邀请、成员角色、资源授权和通知。
- 模型连接、网关、路由、用量、额度、插件和技能目录。

#### 管理层

- 用户、部门、岗位、角色、菜单、字典、公告。
- 登录日志、审计、会话、管理员 MFA 和恢复码。
- 模型连接、模型路由、密钥托管、预算和用量分析。
- 管理工作台、接入检查、团队管理、权限治理和安全页面。

#### 最近已经出现的实现候选

- Incident 后端领域：事件状态、SLA、告警幂等桥接、评论、时间线、关系、指派和关闭复盘字段。
- 工具能力目录：工具版本、真实/模板/不可用状态、输入输出 Schema、风险、权限、凭据引用、截止时间、输出预算、幂等和核验方式。
- Run 治理：幂等键、attempt、deadline、lease、heartbeat、取消、输出截断、`UNCERTAIN` 和过期恢复扫描。
- Sentinel 有界调度：租约、条件认领、固定线程池、信号量背压、退避和抖动。
- 指标与发布基础：Prometheus 指标出口、AI Service 指标、Dockerfile、Compose、Kubernetes 探针和优雅停机配置。
- 云资产与轻量 CMDB：阿里云 ECS 只读清单、资源 UID、增量同步、`ACTIVE/MISSING/DELETED/STALE`、关系和业务影响视图。
- Recovery Contract：七对象、三值求值、探针调度、窗口回执、失效语义和同证据回放候选实现。
- Loopback 机制演示：四类受控场景和回放一致性证据。

### 1.2 当前不能直接写成“已完成”的事项

- 默认聊天入口、Java Assistant、Python AI Service、Knowledge 和 Agent 是否已经形成生产级统一链路，仍需真实请求逐层核对。
- Incident 后端已有实现，但前端页面、真实登录主体、scope、审计、并发状态更新和 Sentinel 真实联动仍需验收。
- 阿里云适配使用替身响应测试，尚未使用真实云账号；腾讯云、华为云只是契约占位。
- 云资产前端页面、集群、负载均衡、数据库等资源采集尚未完成。
- Sentinel 调度尚未完成 1000 任务、慢目标、双副本长期压测。
- Prometheus/AI `/metrics`、Compose 和 Kubernetes 变更尚未完成完整部署验证。
- Recovery Contract 尚未接入 Java 权威 Run、Inspector 和真实生产 mTLS/身份。
- Recovery 前端三张卡、独立 oracle、正式评测和集成审阅尚未完成。
- Knowledge readiness、租户过滤、版本过滤、删除、重启一致性和引用回溯尚未形成完整证据。
- `SCORE-01` 计分器仍有缺字段、双缺字段、合法 `false` 和未知分母问题。
- formal Golden、独立 REAL baseline、训练门禁仍处于 `BLOCKED`。
- 真实 Provider E2E、真实浏览器登录、Java ↔ Python E2E 尚未完成。
- 多租户、服务目录、备份恢复、通知中心、值班升级和完整工单前端仍需继续建设。

### 1.3 当前工作区风险

- 工作区存在大量未提交修改和未跟踪文件。
- 部分改动来自不同并行模型，来源、所有权和验证状态可能不同。
- Java 侧验证依赖 JDK 17；若当前环境没有 JDK 17，必须标记 `BLOCKED/NOT_RUN`。
- 外部 GitHub 实时核验曾受网络/审批环境阻断，历史材料和实时核验必须分账。
- 任何接单模型都必须先保存自己的文件前像，不得以当前 Git HEAD 代替工作区前像。

---

## 2. 总体目标架构和状态边界

### 2.1 四条必须分开的状态轴

| 状态轴 | 说明 | 示例 |
| --- | --- | --- |
| 动作轴 | 动作本身有没有执行 | `PLANNED/PENDING_APPROVAL/APPROVED/RUNNING/SUCCEEDED/FAILED/DENIED/CANCELLED` |
| 纠察轴 | Inspector 是否完成了核验，核验原始结果是什么 | `NOT_CHECKED/PASS/FAIL/UNKNOWN`，保留 raw passed |
| 恢复轴 | 业务是否达到恢复契约 | `VERIFIED/CONTRADICTED/INSUFFICIENT/EXPIRED/INVALIDATED` |
| 授权轴 | 谁在什么范围内，以什么许可执行 | `SUBJECT/SCOPE/GRANT/EXPIRED/CONSUMED/REVOKED` |

目标关系：

```text
用户/告警
  → 资产和目标确认
  → Incident
  → RecoveryContract / Diagnosis
  → Runbook / Approval
  → 权威 Run
  → 工具执行
  → Inspector / Evidence
  → Recovery Receipt
  → Incident 关闭或人工接管
  → 审计和知识沉淀
```

### 2.2 证据平面

所有结论都要能回指：

- `observation_id`
- `run_id`
- `incident_id`
- `asset_uid`
- `scope`
- `binding_revision`
- `source`
- `collected_at`
- `expires_at`
- `evidence_hash`
- `failure_reason`

原因码至少区分：

```text
MISSING / STALE / WRONG_TARGET / WRONG_REVISION / TIMEOUT /
MALFORMED / PERMISSION_DENIED / SOURCE_CONFLICT /
PARTIAL / INTERRUPTED / BUDGET_EXHAUSTED / UNKNOWN
```

---

## 3. 总体批次和依赖图

```text
A0 工作区与事实基线
 ├─ A1 安全/权限/SSRF审计
 ├─ A2 测试/构建/启动/回滚门禁
 ├─ A3 数据许可与独立oracle协议
 └─ A4 开源参考重新核验

B0 状态和契约冻结
 ├─ B1 Java权威Run与四轴状态
 ├─ B2 Recovery Contract 接口
 ├─ B3 Incident/Asset/Scope 关联
 └─ B4 Knowledge readiness契约

C0 可信机制实现
 ├─ C1 三值求值与原因码
 ├─ C2 探针与预算调度
 ├─ C3 窗口核验与回执失效
 ├─ C4 同证据回放
 └─ C5 独立oracle和反例

D0 平台接线
 ├─ D1 Java ↔ AI ↔ Knowledge ↔ Agent
 ├─ D2 Incident 前端和告警桥接
 ├─ D3 CMDB/云资产前端和同步
 ├─ D4 Inspector/Run/Recovery UI
 └─ D5 跨层 trace 和故障矩阵

E0 生产化验证
 ├─ E1 真实登录浏览器 E2E
 ├─ E2 真实 Provider E2E
 ├─ E3 重启/断线/超时/部分成功恢复
 ├─ E4 备份恢复演练
 └─ E5 安全、性能和发布门禁

F0 产品扩展
 ├─ F1 工单/SLA/值班
 ├─ F2 Runbook/变更/发布
 ├─ F3 集成中心
 ├─ F4 多租户与报表
 ├─ F5 服务目录与拓扑
 └─ F6 插件、成本和商业化
```

---

## 4. 阶段 A：事实基线和任务协调

### A-00 总体事实盘点（HC-00）

**当前状态：** `IN_PROGRESS`，已有 v0；需要补 Java ↔ Python 调用链和真实 UI 反查。

**目标：** 生成当前工作区、路由、进程、测试、数据库、服务边界、文档证据的唯一索引。

**任务：**

- [ ] 扫描当前源码、测试、脚本、迁移、前端路由和接口。
- [ ] 记录每个模块的 `REAL/TEMPLATE/MOCK/UNAVAILABLE`。
- [ ] 记录每个能力的 design/implementation/verification 三态。
- [ ] 对照 README、架构文档、代码和运行日志，标记口径不一致。
- [ ] 记录默认聊天入口实际经过哪些服务。
- [ ] 记录 `/api`、`/ai`、内部令牌、SessionUser、`X-User-Id` 等身份边界。
- [ ] 检查 Server、Inspector、Knowledge、Team、Model、Operation 查询是否有统一 scope。
- [ ] 记录当前数据库 migration、表结构和已存在数据。
- [ ] 生成 `inventory.json`、route map、test matrix、status baseline。

**验收：** 每个后续任务能从基线找到输入文件、真实入口、验证命令和当前状态；不能用“代码存在”代替“运行可用”。

**交付：** `docs/audit/20261105/` 或新版本等价目录中的清单、哈希、链接和未决问题表。

### A-01 工作区所有权和变更隔离

**目标：** 避免多模型互相覆盖。

- [ ] 记录每个任务的 owner、写入目录和允许修改文件。
- [ ] 每个任务保存前像 hash 和工作区快照。
- [ ] 共享接口先由协调者冻结，其他模型只消费。
- [ ] 迁移、启动脚本、认证、Run、审计和模型计费列为高影响文件。
- [ ] 为每个任务建立回滚脚本，不回滚其他任务文件。
- [ ] 形成“待合并、已验证、待复核、已废弃”目录。

### A-02 现有文档清理和口径合并

- [ ] 统一 `SmartOpsAgent`、智维 Agent、版本号和端口说明。
- [ ] 合并重复路线图，给历史结果加日期和 `HISTORICAL` 标签。
- [ ] 把“已配置、已连通、已批准、已执行、已验证、已恢复”分开描述。
- [ ] 所有文档引用当前文件路径，不引用已经删除的页面或旧端口。
- [ ] 生成总任务看板，链接各个领域任务书。

---

## 5. 阶段 B：平台架构、身份、Run 和状态机

### B-01 平台权威 Run 和四轴状态机（HC-01）

**当前状态：** `NOT_STARTED`，已有 Run 治理局部实现，需要统一设计。

**目标：** 让 Java 侧成为权威 Run、身份、scope 和审批事实来源。

**必须定义：**

- [ ] Run 的创建、计划、审批、领取、执行、取消、超时、过期、恢复和关闭。
- [ ] 动作轴、纠察轴、恢复轴、授权轴分别存储。
- [ ] Run 与 Incident、Asset、Runbook、Approval、Evidence 的关系。
- [ ] `run_id`、`parent_run_id`、`attempt`、`idempotency_key`、`deadline_at`、`lease_expires_at`、`heartbeat_at`。
- [ ] 状态转移的合法边和非法边。
- [ ] 重复请求、重复审批、重复消费和并发更新的处理。
- [ ] 重启、进程崩溃、远端已执行但本地超时的 `UNCERTAIN` 语义。
- [ ] 取消是本地停止派发，还是远端动作也有取消确认。
- [ ] Run 状态与 SSE 状态、历史状态和审计状态的映射。

**验收：**

- [ ] 退出码 0 但业务字段失败时不能得到 `recovery=VERIFIED`。
- [ ] 远端写操作超时不得自动重试，必须进入 `UNCERTAIN` 并要求核验。
- [ ] 重复幂等键只产生一个有效 Run。
- [ ] 旧审批不能执行新参数。
- [ ] Run 重启后可恢复或明确为中断，不生成假成功。

### B-02 服务间身份和上下文信封

**目标：** 统一主体、租户、团队、scope、请求、任务和 Run。

**任务：**

- [ ] 定义内部上下文信封字段和版本。
- [ ] 区分浏览器 SessionUser、内部服务身份、工具身份和云账号身份。
- [ ] 服务端覆盖客户端伪造的 user、team、tenant、run、scope header。
- [ ] AI、Knowledge、Agent 请求携带签名或受保护的上下文。
- [ ] 过期 token、伪造 run_id、跨团队 scope、错误 owner 全部拒绝。
- [ ] 明确哪些请求可以匿名、哪些必须登录、哪些必须内部令牌。
- [ ] 日志中只保留脱敏主体和范围，不记录凭据和私有正文。

**验收：** 两个用户先后/并发查询同一资源时，不能因全局事件投影或 `MAX(id)` 取值产生串单。

### B-03 Server、Inspector、Knowledge、Team 统一 scope

- [ ] 为主机、指标、Inspector 事件、Run、Incident、资产、知识、模型连接定义归属。
- [ ] 区分全局资产、个人资产、团队资产和租户资产。
- [ ] 每个 GET 查询写出 scope 规则，而不是只在前端隐藏按钮。
- [ ] 检查服务层、Repository、SQL 和分页查询是否都带 scope。
- [ ] 批量查询不能先查全量再在内存过滤敏感数据。
- [ ] 事件、知识反馈和个人记忆不能因 GET 被重复写入或越权写入。

### B-04 并发、幂等和生成 ID

- [ ] 排查 `MAX(id)` 取刚插入 ID 的并发风险。
- [ ] 使用 generated keys 或显式 UUID 绑定当前 insert。
- [ ] 给 review、feedback、memory、crawl、incident comment、notification 增加唯一键或幂等键。
- [ ] 重复 10 次请求和单次请求的结果应一致。
- [ ] 事务失败不能留下半条成功关系或错误 owner 数据。

---

## 6. 阶段 C：安全、权限、SSRF 和审批

### C-01 安全与权限全面审计（HC-02）

**当前状态：** 设计已有 `DONE`，约 15 条风险、27 个入口、32 个负例；验证 `NOT_RUN`。

**任务：**

- [ ] 建立匿名、普通用户、团队成员、团队管理员、平台管理员、特殊管理员的权限矩阵。
- [ ] 每个写接口标注登录入口、平台能力、RBAC、团队角色、资源授权和数据范围。
- [ ] 验证数据库权限表异常时是否 fail closed。
- [ ] 检查历史 admin/ROOT 兼容逻辑是否会隐式提权。
- [ ] 检查管理员确认密码、MFA、CSRF、会话吊销和重放保护。
- [ ] 检查登录、改密、冻结、撤销、审批、执行、凭据读取和导出权限。
- [ ] 形成允许用例和拒绝用例，拒绝用例必须实际得到 401/403/409 等预期结果。

### C-02 SSRF、网络采集和资源边界

- [ ] 解析 URL 每一跳的 DNS、IPv4、IPv6、内网地址和重定向。
- [ ] 防止 DNS rebinding、IPv4-mapped IPv6、十进制 IP 和主机名绕过。
- [ ] 固定出口策略，限制协议、端口和目标类型。
- [ ] 限制请求总时长、连接时长、读取体积、页数、并发和速率。
- [ ] 防止 slow-drip、超大 body、压缩炸弹和无限分页。
- [ ] 响应流式读取并截断，不一次性载入未知大小内容。
- [ ] 外部采集错误不回显上游敏感响应体。
- [ ] 对重定向、私网、回环、云元数据地址和解析失败保存拒绝证据。

### C-03 审批快照与执行绑定

- [ ] 审批预览保存不可变计划摘要、参数摘要、目标快照和版本。
- [ ] 执行前重新验证 digest、scope、审批人资格、许可有效期和团队状态。
- [ ] 禁止自批、过期批准、冻结团队执行、跨团队执行和重复消费。
- [ ] 一次性 grant 消费成功或失败都有明确结果。
- [ ] 审批通过不等于执行成功，执行成功不等于业务恢复。
- [ ] 前端展示批准摘要和实际执行摘要的差异。

### C-04 Secrets 和凭据治理

- [ ] 统一 SSH、数据库、云平台、模型和 Webhook 凭据引用。
- [ ] 凭据元数据与密钥材料分离。
- [ ] 读取只返回名称、类型、状态、更新时间和过期时间。
- [ ] 支持轮换、撤销、过期、租约和按团队/资产授权。
- [ ] 凭据使用有审计事件，但不记录明文。
- [ ] 评估 OpenBao/Vault，仅做隔离 PoC 后决定是否引入。
- [ ] 轮换失败、旧凭据失效和服务恢复流程可演练。

---

## 7. 阶段 D：Incident、告警、SLA 和值班

### D-01 Incident 后端完整验收

**当前状态：** `PARTIAL`。后端已有候选实现和测试，前端未完成，真实 scope/SessionUser/审计/并发仍待核验。

**已有候选能力：**

- `OPEN/ACK/MITIGATING/RESOLVED/CLOSED`。
- SLA deadline 扫描。
- Sentinel 告警幂等桥接。
- 评论和事件时间线。
- 资源关系、指派、关闭根因、处置和复盘字段。

**后续任务：**

- [ ] 将 actor 从请求参数切换为可信 SessionUser/内部主体。
- [ ] 给 Incident 所有查询和修改加团队/租户/scope。
- [ ] 状态更新使用条件更新，防止两个操作者覆盖状态。
- [ ] 定义状态迁移表和非法迁移错误。
- [ ] 检查 SLA 时间使用统一时区和持久时间，不依赖本地机器时间。
- [ ] 关联 Alert、Asset、Run、Evidence、Knowledge 和 Change。
- [ ] 审计创建、指派、转派、评论、状态变更、关闭和复盘。
- [ ] 实现前端 Incident 列表、详情、时间线、指派、评论和关闭表单。
- [ ] 处理空状态、无权限、过期 SLA、并发冲突和失败重试。

### D-02 告警生命周期

- [ ] 告警唯一指纹和来源标识。
- [ ] 去重、分组、合并、抑制和恢复关联。
- [ ] 静默规则、维护窗口、TTL、撤销和到期。
- [ ] 告警确认、负责人、升级链和交接。
- [ ] 告警到 Incident 的幂等创建。
- [ ] 告警恢复不能自动伪造业务恢复，需由恢复契约或业务探针确认。
- [ ] 外部通知失败不显示发送成功。
- [ ] 保存原始告警、归并结果和通知记录。

### D-03 通知和集成适配器

优先级：

1. Webhook。
2. 邮件 SMTP。
3. 企业微信。
4. 钉钉。
5. 飞书。
6. PagerDuty/兼容值班系统。

每个适配器必须有：

- [ ] 配置校验和连通测试。
- [ ] 签名/Token 脱敏。
- [ ] 超时、重试、退避、幂等和死信记录。
- [ ] 消息模板和事件类型。
- [ ] 发送成功、上游接受、用户实际收到三种状态区分。
- [ ] 配置变更审计和回滚。

### D-04 值班、升级和 SLA

- [ ] 值班人员、轮值表、交接时间。
- [ ] 事件等级和响应/恢复目标。
- [ ] 超时升级到下一值班人或负责人。
- [ ] 免打扰、维护窗口和应急通道。
- [ ] MTTA、MTTR、SLA 达成率统计。
- [ ] 节假日、时区和夏令时规则。

---

## 8. 阶段 E：资产、云资源和 CMDB

### E-01 云账号和凭据引用

**当前状态：** `PARTIAL`。阿里云 ECS 只读适配和测试已有；腾讯/华为是占位；真实账号未跑。

- [ ] 云账号、地域、项目、团队、负责人和 `credential_ref`。
- [ ] 只读权限最小化。
- [ ] 分页、429/5xx 退避、401/403 分类。
- [ ] 凭据不出现在响应、日志、异常和签名调试信息。
- [ ] 未实现厂商返回 `SKIPPED/CLOUD_PROVIDER_NOT_IMPLEMENTED`，不能显示空同步成功。
- [ ] 真实账号测试必须使用隔离账号和只读权限。

### E-02 轻量 CMDB

**当前状态：** `PARTIAL`。资源 UID、同步、状态、关系和业务影响后端已有；前端和多资源类型缺失。

- [ ] 统一 `resource_uid` 和资源类型。
- [ ] 主机、ECS、虚拟机、容器、Kubernetes、数据库、负载均衡、域名、IP。
- [ ] `ACTIVE/MISSING/DELETED/STALE/PARTIAL` 状态。
- [ ] 同步 run、分页、失败原因和数据新鲜度。
- [ ] 资源负责人、环境、业务、团队和标签。
- [ ] 关系边：`DEPENDS_ON/HOSTED_ON/ROUTES_TO/MEMBER_OF/RUNS_ON`。
- [ ] 声明关系必须有变更单号或证据。
- [ ] 业务影响视图标注数据不完整账号和过期资源。
- [ ] 前端资源列表、详情、关系图、同步历史和业务影响页面。

### E-03 资产发现和人工确认

- [ ] 自动发现结果先进入候选区。
- [ ] 人工确认、合并、忽略和删除。
- [ ] 重复资源合并规则。
- [ ] 资源身份变更和重命名历史。
- [ ] 失联和删除不能直接物理删除证据。
- [ ] 资产数据进入 Agent 目标选择前必须经过 scope 验证。

### E-04 服务目录和拓扑（P2）

- [ ] 服务、组件、环境、负责人、仓库、发布和 Runbook。
- [ ] 服务健康、依赖、告警、Incident、知识和运行记录统一入口。
- [ ] 只显示有证据的关系，未知关系单独标记。
- [ ] 支持服务影响分析和变更影响预览。

---

## 9. 阶段 F：Runbook、工具和远程执行

### F-01 工具能力目录验收

**当前状态：** `PARTIAL → 接近 DONE`。目录和 Python 插件分派已实现并有定向测试，但模板工具仍未接真实适配器。

- [ ] 后端和前端完全由同一工具目录驱动。
- [ ] 清理或标记前端 `UI_ONLY` 展示型条目。
- [ ] 为每个工具声明版本、实现状态、目标类型、输入/输出 Schema、风险、scope、凭据、deadline、输出上限、幂等和核验。
- [ ] `REAL/TEMPLATE/UNAVAILABLE/UI_ONLY` 行为一致。
- [ ] 非 `REAL` 工具不能进入实际执行。
- [ ] 同名工具启动即失败，不能被 Map 静默覆盖。
- [ ] 异步插件和同步旧工具分派行为一致。

待补真实适配器：

- [ ] `knowledge-retrieval`。
- [ ] `database-readonly`。
- [ ] `grafana-dashboard`。
- [ ] `mysql-slow-query`。
- [ ] `alerts-suppress`。

### F-02 Run 治理和恢复

**当前状态：** `PARTIAL`。幂等、租约、心跳、deadline、取消、输出截断和 `UNCERTAIN` 已有实现；跨 Incident/TeamAgent/Recovery 未完全接线。

- [ ] 统一 Java Run 和 TeamAgentRun 的权威关系。
- [ ] 运行前绑定审批 digest、目标快照和凭据引用。
- [ ] 每条命令保存开始、结束、退出、输出摘要和证据。
- [ ] 写操作超时进入 `UNCERTAIN`，不盲目重试。
- [ ] 取消在命令边界生效，远端停止另有确认。
- [ ] lease 过期后生成 `RUN_STALE`，不自动重试副作用。
- [ ] 运行输出有字节预算、截断标记和脱敏。
- [ ] 运行历史支持分页、筛选、关联 Incident 和恢复结论。

### F-03 Runbook 定义

- [ ] Runbook 版本、状态、作者、审核人和发布记录。
- [ ] 输入参数类型、默认值、枚举、敏感字段和校验。
- [ ] 目标选择器、环境限制和资源快照。
- [ ] 前置检查、动作步骤、后置检查、人工确认点。
- [ ] 回滚步骤和“回滚自身不确定”状态。
- [ ] 单目标、批量、金丝雀、暂停、继续和取消。
- [ ] 并发上限、超时、重试、退避和失败停止策略。
- [ ] 计划任务、告警触发和手工触发。
- [ ] 版本发布必须经过审核，历史 Run 绑定旧版本。

### F-04 执行结果和业务恢复

- [ ] 工具成功、审批批准、Inspector PASS、探针健康和业务恢复分开。
- [ ] 业务恢复必须有独立业务探针或恢复契约。
- [ ] 验证失败、证据不足、超时和未知结果进入人工接管。
- [ ] 不因为命令退出 0 或 Pod Ready 就关闭事件。

---

## 10. 阶段 G：Recovery Contract、Inspector 和创新机制

### G-01 Recovery Contract（N01）

**当前状态：** 设计 `DONE`，七对象和反例已存在；生产接线未完成。

七个对象：

```text
RecoveryContract
Claim
EvidenceObservation
ObligationResult
ProbeDecision
VerificationReceipt
ReplayBundle
```

- [ ] 冻结 schema、字段类型和版本。
- [ ] 冻结 scope、target、revision、template version、obligations、window、budget、TTL。
- [ ] 冻结 TRUE/FALSE/UNKNOWN 和原因码。
- [ ] 拒绝空义务集、缺业务谓词、非法来源和 malformed payload。
- [ ] 旧 binding revision、错 target、未来时间、重复 observation、跨 scope 全部拒绝。
- [ ] `passed` 保留原始含义，不直接映射为恢复。

### G-02 三值求值器（N02）

**当前状态：** 候选已审阅，约 126 pass/1 skip；需要独立复核和接入。

- [ ] 有效业务反例判 `FALSE`。
- [ ] 缺失、过期、超时、未确认身份判 `UNKNOWN`。
- [ ] 存在必需 FALSE → `CONTRADICTED`。
- [ ] 全部必需 TRUE 且窗口完整、无反例 → `VERIFIED`。
- [ ] 其他情况 → `INSUFFICIENT`。
- [ ] 空义务集绝不能 `all([])=True`。
- [ ] 输出证据引用和拒绝原因。

### G-03 探针和预算调度（N03）

**当前状态：** 候选实现和 loopback 有证据；真实 transport、权限和 mTLS 未接。

- [ ] 探针目录声明目标、权限、成本、只读、超时和覆盖义务。
- [ ] 先做 scope、权限、目标白名单、deadline 过滤。
- [ ] 再按覆盖权重/成本、成本、probe_id 固定排序。
- [ ] 采样槽未到时输出 `WAIT(next_eligible_at)`，不能忙轮询。
- [ ] 预算耗尽输出 `STOP/BUDGET_EXHAUSTED`。
- [ ] 调度策略与固定顺序策略同预算对照。
- [ ] 没有独立收益证据时，不宣称节省成本或全局最优。

### G-04 窗口核验和回执（N04）

**当前状态：** 回执和失效测试已有；`expires_after` 未强制，需修复并验证。

- [ ] 三组双路径采样满足窗口才签发 `VERIFIED`。
- [ ] 缺样、中断、过期、旧 revision 和错目标不能凑数。
- [ ] `valid_until` 取 receipt TTL 和 evidence TTL 的最小值。
- [ ] 反例出现时回执追加失效记录，不删除历史。
- [ ] 重启无法继承单调时钟时标记中断/不足。
- [ ] 旧 ACTIVE 不自动复活，必须开新 round。

### G-05 同证据回放（N05）

**当前状态：** 候选文件存在，需确认当前测试和状态。

- [ ] ReplayBundle 固定原始观测、规则、契约、策略、逻辑时间和预算。
- [ ] 回放期间禁止联网、模型调用和真实工具。
- [ ] 100 次同证据回放结果一致。
- [ ] 缺探针、不兼容 schema、缺策略返回 `REPLAY_INCOMPLETE`。
- [ ] 差分回放明确显示改变了哪条义务、证据或策略。

### G-06 Java Run/Inspector 接入（N06）

- [ ] Java 权威 Run 创建 RecoveryContract。
- [ ] Agent/工具观测回写 EvidenceObservation。
- [ ] Inspector 输出 raw result 和恢复 verdict 两套字段。
- [ ] Incident 和 UI 可查询回执、缺口和失效。
- [ ] 认证、scope、run_id、审计和幂等全部接入。

### G-07 三张恢复卡（N07/HC-06）

前端三张卡：

1. **缺口卡**：缺少哪些义务、原因、下一探针、预算、等待时间。
2. **契约卡**：目标、版本、窗口、有效期、当前结论。
3. **回放卡**：原始证据、策略差异、结果、是否完整。

- [ ] HTTP 200 + 业务 false 显示未恢复。
- [ ] `UNKNOWN`、`CONTRADICTED`、`EXPIRED`、`INVALIDATED` 分开显示。
- [ ] 刷新、断线和重试不丢 Run。
- [ ] fixture、mock、real 显示明显标签。
- [ ] 375/768/1440、键盘、深浅色、reduced-motion 验收。

### G-08 独立 oracle 和主张收敛（N08/N09）

- [ ] oracle 不读取模型自评、候选求值器或 UI 结论。
- [ ] 真实健康、动作完成、证明充分性分开标注。
- [ ] 强基线、固定顺序、调度策略和回放策略预注册。
- [ ] 未证明的“优化、节省、自动修复、全局最优”从答辩主张中删除。

---

## 11. 阶段 H：Knowledge/RAG 和数据生命周期

### H-01 Knowledge readiness（HC-04）

**当前状态：** `NOT_STARTED/PARTIAL`。已有 manifest、SQLite 持久层和 ACL 预留，但 readiness 和运行实例一致性需验收。

- [ ] readiness 返回 corpus version、manifest hash、chunk count、index version、last build、scope。
- [ ] 服务可访问和索引可用分开。
- [ ] 空索引、部分加载、加载失败和旧版本明确显示。
- [ ] 重启前后同查询结果一致。
- [ ] 版本过滤、租户过滤、团队过滤和权限过滤可复现。
- [ ] 删除/撤回后不再命中。
- [ ] 结果可回到文档、chunk、版本和 evidence hash。

### H-02 摄入和采集

- [ ] 文档来源、许可、PII、来源人、时间和撤回方式登记。
- [ ] URL、文件、Git、手工输入等来源分开。
- [ ] 解析、分块、嵌入、索引、删除和重建都有版本。
- [ ] 单文件大小、总量、页数、字符数、并发、超时和速率限制。
- [ ] 采集失败不产生绿色知识条目。
- [ ] 重新摄入可识别重复、版本和来源变更。

### H-03 检索质量

- [ ] source-level 和 chunk-level 口径分开。
- [ ] Recall@1/3/5、MRR、nDCG、Precision、引用 coverage。
- [ ] 引用 entailment、版本误召回和权限误召回。
- [ ] `trust_score`、retrieval score、citation support、model confidence 分开。
- [ ] 低证据时明确拒答或要求补证。
- [ ] RAG 结果与最终回答的引用保持一致。

### H-04 持久向量库评估

先做适配层和隔离 PoC，不默认引入 Qdrant。

- [ ] 同语料对比当前实现和候选库。
- [ ] 重启恢复、过滤、删除、更新和导出。
- [ ] 多租户隔离和权限过滤。
- [ ] 延迟、内存、磁盘、部署和迁移成本。
- [ ] 失败、降级、回滚和退出。
- [ ] 没有可测收益时保持当前实现。

---

## 12. 阶段 I：AI Service、模型网关和对话契约

### I-01 真实聊天链路核对

- [ ] 浏览器请求 → 前端代理 → Java/AI Service 的真实路径取证。
- [ ] 记录当前默认入口是否经过 `AssistantController → MiniAssistantEngine`。
- [ ] 记录直连 `8001` 的接口是否有用户身份和内部令牌校验。
- [ ] 统一聊天入口或明确两条入口的边界。
- [ ] 不把一条链路的功能描述成另一条链路已经具备。

### I-02 ChatRequest 和 SSE envelope

- [ ] 统一 prompt、conversation、model、provider、attempt、request_id、run_id。
- [ ] thinking、token、citation、diagnostic、run_event、done、error 事件 schema。
- [ ] 顶层和 metadata 的 run_event 位置统一。
- [ ] 空流、首 token 后中断、502、Knowledge 503、模型超时有明确终态。
- [ ] 重试不重复追加用户消息或答案。
- [ ] 多轮历史、模型切换和刷新恢复一致。

### I-03 模型网关和预算

- [ ] provider、model、base URL、密钥、超时、重试和 fallback 记录。
- [ ] 个人 Key、团队额度、平台额度和模型总额度范围分开。
- [ ] 并发额度预占、成功结算、失败释放和未知 usage 口径冻结。
- [ ] unknown usage、失败调用、空回复、pending 计量规则明确。
- [ ] 模型健康、真实调用、fixture 和 mock 分开。
- [ ] 模型配置修改有审计、版本和回滚。

### I-04 AI 观测和成本

- [ ] 记录模型调用延迟、首 token、总 token、错误和降级。
- [ ] 关联团队、用户、Incident、Run 和任务，但不保存完整私有 Prompt。
- [ ] Token/费用报表可按时间、模型、团队和任务查询。
- [ ] 敏感字段白名单和保留期限冻结。
- [ ] 评估 Langfuse/OTel 只做隔离 PoC，不直接引入默认部署。

---

## 13. 阶段 J：Agent、Inspector、工具和记忆

### J-01 Planner

- [ ] 规划输出有版本、目标、步骤、依赖、风险、参数和验证标准。
- [ ] 目标资产必须来自授权资产范围。
- [ ] 计划不能自行改变审批范围。
- [ ] 不确定、证据不足和高风险动作进入人工确认。
- [ ] 规划失败、工具不可用和知识不足分别记录。

### J-02 Executor

- [ ] 只执行已授权、已批准、未过期、digest 一致的步骤。
- [ ] 参数 Schema、目标、凭据、deadline、output limit 和幂等全部强制。
- [ ] 非 REAL 工具拒绝执行并返回稳定错误码。
- [ ] 写操作超时进入 UNCERTAIN，不自动重试。
- [ ] 执行结果脱敏，保留原始输出摘要和证据。

### J-03 Inspector

- [ ] 规则判定、证据判定、AI Judge 和状态核验分层。
- [ ] 保留 raw passed、检查状态、原因、证据来源和时间。
- [ ] Inspector 未执行、证据不足、超时和失败不能被当作 PASS。
- [ ] Inspector 结论不能直接覆盖业务恢复结论。
- [ ] 错目标、旧版本、旧轮次和跨 scope 证据拒绝。

### J-04 Memory 和知识回写

- [ ] 经验写回必须关联 Incident、Run、Evidence 和 reviewer。
- [ ] 重复 review/GET 不重复写入 memory feedback。
- [ ] 自动生成候选不能直接晋升正式知识。
- [ ] 私人知识、团队知识、平台知识范围分开。
- [ ] 经验包含版本、适用环境、风险和失效时间。

### J-05 插件和 MCP

- [ ] 工具发现、Schema、版本、transport 和健康检查。
- [ ] 插件权限、沙箱、超时、输出预算和网络边界。
- [ ] 插件签名、来源、依赖、兼容矩阵、升级和卸载。
- [ ] MCP 工具目标、scope、凭据和审计一致。
- [ ] 插件加载失败不能影响核心服务启动，除非被声明为必需依赖。

---

## 14. 阶段 K：前端用户体验和管理端

### K-01 三张恢复卡和故障时间线

- [ ] 恢复卡接后端权威状态，不在前端推断成功。
- [ ] 事件、Run、探针、回执、审计在一条时间线展示。
- [ ] 失败、拒绝、超时、未知、未配置、人工接管分别展示。
- [ ] 空数据、权限不足、部分数据、网络断开和过期数据可解释。

### K-02 Incident 页面

- [ ] 事件列表：状态、严重级别、负责人、SLA、更新时间、来源。
- [ ] 事件详情：摘要、资产、告警、Run、证据、时间线、评论、复盘。
- [ ] 状态操作、指派、转派、评论和关闭表单。
- [ ] 关闭必须填写根因、处置和复盘。
- [ ] 并发冲突和权限拒绝清晰提示。

### K-03 云资产页面

- [ ] 云账号列表、同步状态、错误和最后更新时间。
- [ ] 资源筛选、分页、状态、环境、业务和团队。
- [ ] 资源详情、关系、来源证据和数据新鲜度。
- [ ] 同步按钮显示真实状态，不把 `SKIPPED/PARTIAL` 变成成功。
- [ ] 业务影响视图显示数据完整性。

### K-04 管理端治理页面

- [ ] 首页卡片显示时间范围、来源、更新时间和可行动入口。
- [ ] 账户处置、权限调整、审计回溯、审批监督、模型治理、知识质量和接入排查形成完整旅程。
- [ ] 管理页面首次进入自动加载且失败不吞错。
- [ ] 密码复核使用安全对话框，不使用原生 prompt。
- [ ] 密码输入在成功、失败、取消、关闭和路由离开后都清空。
- [ ] 管理内链有效，跨门户使用正式切换，不跳到不存在的用户路由。
- [ ] 会话、权限和数据范围变化后清理前端缓存。

### K-05 无障碍和响应式

- [ ] 375/768/1440 宽度。
- [ ] 深浅色主题、200% 缩放。
- [ ] 键盘焦点、快捷键、输入法组合、Esc/Enter/Shift+Enter。
- [ ] reduced-motion。
- [ ] axe serious/critical 为 0。
- [ ] 关键文字对比度满足要求。
- [ ] 大量消息、长文本、长表格和分页不造成明显卡顿。

### K-06 前端真实 E2E

- [ ] 隔离用户、团队和数据库。
- [ ] 登录 → 对话 → 引用 → Incident → 审批 → Run → Inspector → 关闭。
- [ ] 模型切换、流中断、重试、刷新和断线恢复。
- [ ] 管理员账户冻结、会话撤销、权限拒绝和审计。
- [ ] 真实 Provider 和 fixture 明确分账。
- [ ] 保存 Playwright trace、截图、page errors、网络错误和环境摘要。

---

## 15. 阶段 L：数据、评测和数学诊断

### L-01 计分器字段和分母修复（SCORE-01）

**当前状态：** `NOT_STARTED`，已发现具体问题。

- [ ] 双方空字典不产生工具或根指标满分。
- [ ] 不同工具且 `next_tool` 双方缺失不判一致。
- [ ] 缺 `safety_violation` 不当作已观察 `false`。
- [ ] 合法显式 `false` 纳入分母。
- [ ] 预测缺失、超时、系统失败保留失败状态。
- [ ] 每个指标输出 `scored_count/missing_count/total_count`。
- [ ] `null`、`UNKNOWN`、`NOT_APPLICABLE` 和 0 分开。
- [ ] 修复前输入、红测试、修复后结果和回滚保留。

### L-02 数据治理（HC-08）

- [ ] 来源、许可证、PII、血缘、撤回、删除和 hash registry。
- [ ] 训练、开发、验证、测试按事故族、来源、时间隔离。
- [ ] 同源改写、重复事故和候选派生不得跨 split。
- [ ] 双人标注、专家裁决和 review receipt。
- [ ] 模型输入不能读取 oracle、label reason 或答案。
- [ ] approved sample 为 0 时正式指标为 `null/BLOCKED`。

### L-03 独立 Golden 和 REAL baseline

- [ ] 建立人工相关性 Golden。
- [ ] 建立 Inspector/Recovery 独立 oracle。
- [ ] 建立真实 Provider baseline。
- [ ] 建立固定顺序探针 baseline。
- [ ] 建立完整 Inspector、仅规则、仅证据、去版本、去引用等消融。
- [ ] 分别统计失败、拒绝、超时、未知、预算耗尽和人工等待。
- [ ] 不使用模型自评作为唯一标签。

### L-04 数学诊断层（HC-09）

V1 只做确定性方法：

- [ ] 三值约束求值。
- [ ] 证据图和义务覆盖。
- [ ] 权限、scope、目标、版本、freshness、round、deadline 约束。
- [ ] 预算约束探针选择。
- [ ] WAIT/STOP 状态。
- [ ] receipt TTL 和失效。
- [ ] 固定顺序策略对照。

V2 必须满足条件后才做：

- [ ] 有独立校准的假设分布。
- [ ] 有观测结果模型。
- [ ] 包含 timeout/unknown 和相关来源。
- [ ] 有 Brier、ECE、可靠性图和置信区间。
- [ ] 有风险—覆盖曲线和 cluster bootstrap。
- [ ] 没有条件时返回 `NOT_APPLICABLE`，退回 V1。

### L-05 数据漂移和评测统计

- [ ] 记录场景族、来源、模型、Prompt、知识版本和代码 hash。
- [ ] 误放、误暂缓、覆盖、成本、延迟和尾延迟分别统计。
- [ ] 不以平均准确率掩盖全部 UNKNOWN。
- [ ] PSI/JS 只在样本量和分箱稳定时使用。
- [ ] 漂移只触发人工复核，不自动放宽阈值或重训。

---

## 16. 阶段 M：测试、构建、启动和发布门禁

### M-01 统一质量门禁（HC-05）

**当前状态：** 设计已有 `DONE`，执行 `NOT_RUN`。

- [ ] 统一 `PASS/FAIL/SKIP/ERROR/NOT_RUN/BLOCKED`。
- [ ] 真实依赖缺失不能静默 skip。
- [ ] 保存 Node、Python、JDK、Maven、浏览器和 Docker 版本。
- [ ] 前端用户端、管理端、typecheck、lint、构建分别验收。
- [ ] Python root、AI、Knowledge、Agent、training 分开报告。
- [ ] Java 17 环境固定，测试数据库隔离。
- [ ] 全量测试和定向测试不混为一条结论。

### M-02 启动 preflight

- [ ] MySQL/Redis/Java/Python/Node/模型/Knowledge 的版本和配置摘要。
- [ ] 端口只是基础检查，必须额外检查 HTTP readiness 和业务 readiness。
- [ ] Knowledge chunks、manifest、index version 非零且匹配。
- [ ] AI provider、模型、fallback 状态明确。
- [ ] 数据库迁移摘要、镜像 digest 和源码 commit 记录。
- [ ] 所有必需依赖失败时阻止演示或明确切换 fixture。

### M-03 构建和制品

- [ ] Python requirements hash/lock。
- [ ] Node package lock 和审计。
- [ ] Maven 依赖和插件版本。
- [ ] 生成 SBOM。
- [ ] 镜像构建使用固定基础镜像和 digest。
- [ ] 前端构建使用独立输出目录，不删除正在使用的 dist。
- [ ] 用户端和管理端制品独立 hash。

### M-04 回滚和发布

- [ ] 文件回滚、数据库迁移回滚和外部动作回滚分开。
- [ ] 数据库只增量迁移，回滚前先备份和演练。
- [ ] 失败发布保留旧制品运行。
- [ ] Compose/Kubernetes 资源、探针、优雅停机和滚动升级验证。
- [ ] 发布失败、健康失败、探针失败、业务失败分别记录。
- [ ] 新增依赖有退出路径。

### M-05 当前已有但待运行的发布任务

- [ ] 完整应用启动验证 `/actuator/prometheus`。
- [ ] AI Service `/metrics` 真实返回。
- [ ] Docker Compose 全链路启动。
- [ ] Kubernetes startup/readiness/liveness 验证。
- [ ] 优雅停机和摘流验证。
- [ ] 镜像构建和启动日志保存。

---

## 17. 阶段 N：性能、可靠性和容量

### N-01 Sentinel 1000 任务压测

**当前状态：** 代码和定向测试已有；压测 `NOT_RUN`。

- [ ] 1000 个任务、5% 慢目标。
- [ ] 记录 due delay、queue age、p50/p95/p99、失败率和租约回收。
- [ ] 验证固定并发、信号量背压和指数退避。
- [ ] 双副本运行 30 分钟，确认不重复领取。
- [ ] 统计成功、失败、背压推迟、过期和下一次执行时间。

### N-02 Run 负载和输出压力

- [ ] 100 个目标、并发上限 10、10% 失败。
- [ ] 持续输出、100MB 输出和长时间命令。
- [ ] 验证 output limit、截断证据和内存上界。
- [ ] 验证取消、deadline、远端未知状态和重启。
- [ ] 不把连接断开当作远端动作已停止。

### N-03 HTTP/SSH/数据库资源治理

- [ ] FastAPI HTTP transport 复用、连接池、并发闸门和等待。
- [ ] SSH session 复用、idle TTL、失活清理和连接上限。
- [ ] 数据库查询只读、语句超时、行数、字节和脱敏。
- [ ] 查询、日志和输出不把大对象全部载入内存。

### N-04 指标、SLO 和错误预算

- [ ] 服务可用率、错误率、P95、采集新鲜度。
- [ ] Agent 执行成功率、验证成功率和未知率。
- [ ] Knowledge readiness 和检索空结果率。
- [ ] AI 首 Token、总延迟、Provider 错误和降级率。
- [ ] SLO、错误预算、燃烧率和通知。
- [ ] 真实、fixture、mock、degraded 分账。

### N-05 备份和恢复演练

- [ ] MySQL 全量/增量和加密。
- [ ] Knowledge manifest、索引和附件。
- [ ] 审计、Run、Incident、配置和插件。
- [ ] 异地/异机副本、保留周期和删除。
- [ ] 恢复到隔离环境。
- [ ] 记录 RPO、RTO、数量、hash、关联关系和查询结果。

---

## 18. 阶段 O：集成、身份、租户和治理

### O-01 集成中心

- [ ] Prometheus/Alertmanager。
- [ ] Webhook/SMTP/企微/钉钉/飞书。
- [ ] GitHub/GitLab、Argo CD。
- [ ] OIDC、LDAP/AD、SCIM（有企业需求再做）。
- [ ] 每个连接器有配置、测试、状态、超时、重试、审计和回滚。

### O-02 租户和工作区

先做产品决策：单租户多团队，还是多租户 SaaS。

- [ ] tenant/workspace/team/resource scope 统一定义。
- [ ] 资产、知识、告警、Incident、Run、模型、额度、审计全部带 scope。
- [ ] 平台管理员跨租户查询要有明确能力和审计。
- [ ] 导出、删除、保留期限和数据区域策略。
- [ ] 团队冻结后，读取、邀请、审批、执行和退出分别定义。

### O-03 审计与合规

- [ ] 统一 action、outcome、actor、target、request、run、trace、ip、detail。
- [ ] 依据和结果分列。
- [ ] 事件目录覆盖平台任命、撤销、团队邀请、模型、审批、执行、凭据和导出。
- [ ] 审计不可篡改、归档、保留和导出。
- [ ] 密码、Token、完整连接串、私有 Prompt 和敏感日志不进入审计。

### O-04 运营报表

- [ ] MTTA、MTTR、SLA。
- [ ] 告警噪声、重复、静默和恢复。
- [ ] Run 成功、失败、未知、取消、审批等待。
- [ ] Knowledge 命中、引用和版本误召回。
- [ ] 模型 Token、费用、错误和降级。
- [ ] 资产覆盖、过期、缺失和同步失败。
- [ ] 支持 CSV/PDF 导出，导出有权限和审计。

---

## 19. 阶段 P：开源研究和依赖引入

### P-01 开源仓库重新核验

对每个候选记录：

- 仓库 URL。
- 固定 commit/tag。
- 采集时间。
- README 和 LICENSE hash。
- 许可证和 NOTICE。
- 依赖树/SBOM。
- Windows/Linux/Java/Python/Node 兼容性。
- 资源消耗。
- 失败模式。
- 退出和回滚。
- 借鉴机制、适配约束和不采用理由。

### P-02 优先候选

| 候选 | 借鉴内容 | 不直接照搬的边界 |
| --- | --- | --- |
| Alertmanager | 告警分组、抑制、恢复、静默 | 不等于业务恢复证明 |
| NetBox | CMDB、IP、资源关系 | 不覆盖本项目 Agent 审批 |
| Rundeck | Runbook、节点和执行历史 | 不建立第二套执行源 |
| StackStorm | 事件到动作工作流 | 不绕过现有审批和权限 |
| AWX | 作业模板、凭据和批量执行 | 先比较现有 Executor |
| OpenBao | 租约、轮换、动态凭据 | 先做安全和部署 PoC |
| OpenTelemetry | Trace/Log/Metric 管道 | Trace 不等于健康证明 |
| Keycloak | OIDC/LDAP/SSO | 不替换现有身份前先做 ADR |
| Qdrant | 持久向量、payload filter | 没有规模收益不引入 |
| Langfuse | LLM trace 和评测 | 不采集私有 Prompt |
| Promptfoo | Prompt/Provider 回归 | 不替代独立 Ground Truth |
| Velero | 备份恢复 | 先定义 SmartOps 数据集合 |
| Backstage | 服务目录和 owner | P2 阶段再做 |

### P-03 数据集和开源日志

- [ ] AIOpsLab、LogHub 等只做来源研究。
- [ ] 未核验数据条款前不下载、不入库、不进 Golden。
- [ ] 日志异常标签不等于业务恢复真值。
- [ ] 第三方数据集和代码许可证分开审查。

---

## 20. 阶段 Q：竞赛、答辩和交付材料

### Q-01 统一演示主线

推荐主线：

```text
HTTP 200 但业务字段失败
  → 缺口卡
  → 契约卡
  → 预算补证
  → 失败/恢复回放卡
  → 明确为什么不能结单
```

- [ ] 演示不把模型文字、exit 0 或审批通过说成恢复。
- [ ] 展示证据来源、版本、scope、时间窗和有效期。
- [ ] 展示失败、UNKNOWN、过期和人工接管。
- [ ] 真实、fixture、mock 画面有清晰标识。
- [ ] 录制前运行 preflight，保存版本、数据库、模型和语料摘要。

### Q-02 创新主张矩阵

可主张：

- [ ] 运维恢复结论的证据义务。
- [ ] 预算约束的补证选择。
- [ ] 可失效、可追溯的恢复回执。
- [ ] 同证据确定性回放。
- [ ] 失败和未知状态不被伪装成成功。

暂不主张：

- [ ] 全球首创。
- [ ] 第一个算法。
- [ ] 天然因果诊断。
- [ ] 已完成自动修复。
- [ ] 已达到生产准确率。
- [ ] 未验证开源组件已经集成。

### Q-03 材料一致性

- [ ] README、技术文档、演示脚本和 UI 文案一致。
- [ ] 测试数量、模型版本、知识数量和指标都带日期和证据。
- [ ] 历史结果、当前结果、fixture 和真实结果分开。
- [ ] 未完成能力显示为路线图或限制，而不是功能完成。

---

## 21. 大模型分工表

| 角色 | 主要任务 | 不得越界 |
| --- | --- | --- |
| 模型 A：事实基线 | A-00/A-01/A-02 | 不改业务代码，不自行认定完成 |
| 模型 B：平台架构 | B-01～B-04 | 不另建 Run/审批/身份系统 |
| 模型 C：安全审计 | C-01～C-04 | 不关闭鉴权、CSRF、审批或 scope |
| 模型 D：Incident/告警 | D-01～D-04 | 不绕过 Java 权威 Run 和审计 |
| 模型 E：资产/云/CMDB | E-01～E-04 | 不执行真实云写操作，不输出密钥 |
| 模型 F：工具/Runbook | F-01～F-04 | 不把模板工具伪装成 REAL |
| 模型 G：Recovery/Inspector | G-01～G-08 | 不把 passed/exit 0 当恢复 |
| 模型 H：Knowledge/RAG | H-01～H-04 | 不无证据引入向量库，不跨租户检索 |
| 模型 I：AI Service/网关 | I-01～I-04 | 不把直连链路写成统一生产链路 |
| 模型 J：Agent/插件 | J-01～J-05 | 不绕过审批、目标和凭据边界 |
| 模型 K：前端/UX | K-01～K-06 | 不在前端推断后端成功，不伪造数据 |
| 模型 L：数据/评测/数学 | L-01～L-05 | 不改真值刷分，不使用模型自评作 oracle |
| 模型 M：发布/性能 | M-01～M-05、N-01～N-05 | 不以本机通过代替生产部署验证 |
| 模型 N：集成/租户/报表 | O-01～O-04 | 不放宽跨团队或跨租户查询 |
| 模型 O：开源研究 | P-01～P-03 | 不未经许可安装、下载、引入依赖 |
| 模型 P：独立审阅 | 每批审阅和 HC-12 | 不参与起草自己的交付结论 |

---

## 22. 可直接复制给其他大模型的接单提示词

```text
项目：D:/SmartOpsAgent
任务编号：<TASK_ID>
任务名称：<TASK_NAME>
模式：先 PLAN，未经明确授权不得 IMPLEMENT/RUN

请先阅读：
1. AGENTS.md
2. README.md
3. docs/development/SmartOpsAgent-全面体检与大模型任务总清单-20261105.md
4. 与任务编号对应的既有任务书和证据文件

先做以下工作：
1. git status --short、git rev-parse HEAD、环境版本和配置摘要；
2. 定位真实入口、调用链、接口、数据库表、迁移、前端路由和测试；
3. 判断现状为 DONE/PARTIAL/MOCK/NOT_RUN/BLOCKED/NOT_STARTED；
4. 记录已有模型或人工的文件前像 hash；
5. 列出本任务的依赖、独占写入目录和不允许修改的文件。

PLAN 必须交付：
- 现状证据和文件路径；
- 目标、范围和非目标；
- 数据模型、状态机、接口和权限边界；
- 正例、负例、失败、未知和过期语义；
- 验收命令、原始输出位置和回滚方案；
- design_status/implementation_status/verification_status；
- fixture/mock/real/provider_e2e 标记；
- 下一依赖和阻塞条件。

IMPLEMENT/RUN 获准后：
- 先红后绿，保留失败原始证据；
- 每次只改一个主要边界；
- 不覆盖其他模型的工作区修改；
- 不增加第二套用户、权限、审批、Run、审计或计费账；
- 不把 HTTP 200、exit 0、passed、模型回答或审批通过当作业务恢复；
- 不修改 Golden 或测试期望来刷分；
- 不把 fixture/mock/历史结果标成真实生产证据；
- 高影响迁移、启动、认证、跨服务调用先做备份和隔离回滚。

最终必须交付：
1. 改后文件或设计文档；
2. 精确 diff 和文件所有权；
3. 原始验证命令、退出码、环境摘要、失败/跳过原因；
4. hash 保护回滚脚本和副本演练记录；
5. 未完成、NOT_RUN、BLOCKED、UNKNOWN 和下一步依赖。
```

---

## 23. 单项任务卡模板

```markdown
## <TASK_ID> <任务名称>

- owner:
- mode: PLAN / IMPLEMENT / RUN / REVIEW
- priority: P0 / P1 / P2 / P3
- evidence_class: DESIGN / MOCK / FIXTURE / REAL / HISTORICAL
- dependencies:
- exclusive_write_scope:
- forbidden_files:
- design_status:
- implementation_status:
- verification_status:

### 现状

### 目标

### 非目标

### 输入文件和入口

### 数据模型与状态机

### 权限、scope 和审计

### 正例

### 负例

### 失败、未知、超时和过期

### 实施步骤

### 验证命令

### 原始证据位置

### 回滚方式

### 风险和阻塞

### 下一依赖
```

---

## 24. 推荐的实际派发顺序

### 第一批：只读基线和独立审阅

1. `A-00` 当前事实基线 v1。
2. `A-01` 工作区所有权和任务隔离。
3. `C-01` 安全/权限/SSRF 验证计划。
4. `M-01` 测试、构建、启动和回滚门禁执行计划。
5. `L-02` 数据治理协议复核。
6. `P-01` 开源仓库版本、许可证和退出核验。

### 第二批：状态契约和可信机制

1. `B-01` Java 权威 Run 和四轴状态。
2. `B-02` 服务间身份和 scope。
3. `G-01` Recovery Contract 最终冻结。
4. `G-02` 三值求值器独立复核。
5. `G-03` 探针和预算调度复核。
6. `G-04` 回执 TTL/失效修复。
7. `G-05` 回放完整性复核。
8. `L-01` SCORE-01 计分器修复规格。

### 第三批：平台接线

1. `D-01` Incident 后端独立验收和前端页面。
2. `E-02` CMDB 前端和多资源类型。
3. `F-02` Run 与 Incident/Recovery 接线。
4. `G-06` Java Run/Inspector 接入。
5. `H-01` Knowledge readiness 和删除/重启语义。
6. `I-01` 真实聊天链路核对。
7. `D-02` Sentinel 告警到 Incident 和通知链路。

### 第四批：真实环境验证

1. `K-06` 真实浏览器 E2E。
2. `I-02` 真实 Provider E2E。
3. `M-05` Compose/Kubernetes/指标出口。
4. `N-01` Sentinel 压测。
5. `N-05` 备份恢复演练。
6. `C-04` 凭据轮换和泄露演练。

### 第五批：产品扩展

1. `D-03/D-04` 通知和值班。
2. `F-03` Runbook 版本、批量、回滚和调度。
3. `O-01/O-02` 集成和租户。
4. `O-04` 运维报表。
5. `E-04` 服务目录和拓扑。
6. `P-02` 开源机制隔离 PoC。

---

## 25. 总体验收门槛

项目只有同时满足下面条件，才能对外写成“可信 AI 运维闭环已完成”：

- [ ] 真实用户、团队、租户和资产 scope 经过验证。
- [ ] Java、AI、Knowledge、Agent 和前端的 Run/身份链路可追溯。
- [ ] Incident、告警、Run、Inspector、Recovery Receipt 和审计可以互相跳转。
- [ ] 动作成功、Inspector 通过、业务恢复和授权状态分开显示。
- [ ] 审批快照和实际执行参数 digest 一致。
- [ ] 写操作超时进入未知，不盲目重试。
- [ ] Knowledge readiness、版本、租户、删除和重启一致性有证据。
- [ ] 真实浏览器和真实 Provider E2E 与 fixture 分账。
- [ ] 失败、拒绝、超时、部分成功、断线、重启和恢复有明确终态。
- [ ] Golden、oracle、baseline、评测分母和数据许可完整。
- [ ] 备份恢复、发布回滚和依赖退出有演练记录。
- [ ] 开源组件有固定版本、许可证、容量、退出和回滚结论。
- [ ] README、演示、答辩和 UI 文案只陈述已验证事实。

---

## 26. 当前最终判断

SmartOpsAgent 已经拥有较丰富的功能和代码基础，当前最重要的工作不是继续增加页面，而是完成以下四条证据闭环：

```text
资产 → 告警 → Incident → Runbook → 审批 → 执行 → Inspector → 恢复回执 → 复盘
```

```text
用户/团队 → scope → 目标 → 凭据 → 工具 → Run → 审计
```

```text
浏览器 → Java → AI → Knowledge → 模型 → Agent → 工具 → Inspector
```

```text
数据来源 → 许可/PII → Golden/oracle → 评测 → 发布门禁 → 回滚
```

首批最值得交给其他大模型的任务：

- `A-00` 事实基线 v1。
- `C-01` 安全和权限验证。
- `B-01` 权威 Run 与四轴状态。
- `G-04` 回执 TTL 和失效修复。
- `D-01` Incident 前后端闭环。
- `E-02` CMDB 前端和多资源资产。
- `H-01` Knowledge readiness。
- `L-01` SCORE-01 计分器修复。
- `M-01` 当前工作区完整质量门禁。
- `K-06` 真实浏览器 E2E。

