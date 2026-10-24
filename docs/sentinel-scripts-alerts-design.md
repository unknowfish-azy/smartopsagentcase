# 哨兵监控 · 脚本执行 · 告警联动：设计、表结构与协作优化

> 本文回答三件事：**界面与主菜单结构**、**数据库表设计**、**多人协作（共享 Agent）优化方案**，
> 并明确哪些能力**复用既有代码**、哪些是**本次真正新增**。
>
> 设计原则：与项目既有理念一致 ——
> `监测 → 分析 → 知识检索 → 证据验证 → 决策规划 → 风险判断 → 人工审批 → 安全执行 → 结果验证 → 审计留痕`。
> 因此**告警联动绝不旁路审批直接执行**：AI 只做研判与推荐，高危/P0 一律人工确认。

---

## 一、先看清：哪些已经有了，不要重复造

在动手前对现有代码做了盘点，结论如下。

| 需求 | 现状 | 结论 |
| --- | --- | --- |
| 在远程资产上执行命令 | `MultiExecController` + `MultiExecService`：`/preview` 出预览与 `confirmationNonce`，`/execute` 需 nonce（生产目标还要二次 nonce） | **复用为唯一执行出口**，不新建执行器 |
| 审批流 | `TeamAgentRunService`：`draft → publish → preview → approve → execute`，含 pending approvals | **复用**，告警处置走同一条链 |
| AI 研判 | `IncidentRecommendationService`、`VisionHandoffService` | **复用**，只把告警 payload 接进去 |
| 通知 | `TeamNotificationService`、`TeamActivityService` | **复用**，告警事件发布到这里 |
| 指标采集 | `ServerMetricService`（仅瞬时快照，362 字节）、`ObservabilityService`（Prometheus/Loki 查询） | 有采集但**无历史、无阈值、无常驻** |
| 执行记录/审计 | `OperationRunQueryService`、`JdbcOperationRunRecorder`、`SecurityAuditService` | **复用** |
| 多人协作共享 Agent | `TeamAgentService`（草稿/发布）、`TeamWorkspaceService`、团队会话与运行 | 已有基础，见第四节优化 |
| **常驻哨兵引擎** | **不存在**（全仓 `sentinel`/`@Scheduled`/阈值/防抖 零命中） | **本次新增** |
| **脚本注册表**（版本/标签/黑名单/参数） | 不存在，现有只有"一条命令" | **本次新增** |
| **告警规则与告警中心** | 不存在 | **本次新增** |
| **时序指标历史** | 不存在 | **本次新增** |

所以本次新增的边界很清楚：**哨兵引擎 + 脚本注册表 + 告警中心 + 指标历史**，
其余全部复用。这样既满足需求，又不破坏既有安全链。

---

## 二、主菜单与界面结构

侧边栏新增**一个**顶级分组（与既有 `AGENT` / `MEMORY` 折叠组同构），三个模块作为其子项，
避免一次性把侧边栏塞爆：

```
SENTINEL / 哨兵与自动化        ← 新增顶级分组
├── SENTINEL DASHBOARD  哨兵监控台   /sentinel
├── SCRIPT LIBRARY      脚本库       /sentinel/scripts
└── ALERT CENTER        告警中心     /sentinel/alerts
```

现有顶级入口保持不变。`ADMIN` 与 `ARCHITECTURE` 仍限管理员。

### 2.1 哨兵监控台 `/sentinel`

| 区块 | 内容 |
| --- | --- |
| 概要卡 | 在线哨兵数 / 离线 / 今日告警 / 采集成功率 |
| 监控对象列表 | 资产或资产分组，逐个显示哨兵状态、最近采集时间、采集周期、启停开关 |
| 采集周期 | 秒级 / 分钟级选择，单对象或批量下发 |
| 阈值模板 | 可复用模板（如「内存>90%」），支持批量应用到多台资产 |
| 指标曲线 | 时序曲线，异常点标红；无历史数据时给空态而不是假曲线 |
| 日志哨兵 | 监听日志路径 + 关键字（ERROR/Exception/宕机），命中即产生告警 |

### 2.2 脚本库 `/sentinel/scripts`

| 区块 | 内容 |
| --- | --- |
| 脚本列表 | 名称、语言、标签、版本、风险级别、最近执行结果 |
| 在线编辑器 | Shell / Python / Bat / PowerShell |
| 版本与标签 | 每次保存产生新版本，可回看与回滚；标签用于分类与检索 |
| 风险预检 | 保存与执行前做语法预检 + 高危命令黑名单（`rm -rf`、格式化等），命中即拒绝并说明 |
| 角色权限 | 不同角色只能查看/执行被授权的脚本 |
| 三种执行模式 | 手动执行（选目标资产、实时输出）；定时执行（cron）；告警联动（由告警规则触发） |
| 平台变量 | `${主机IP}` `${告警指标}` `${告警值}` `${告警级别}` `${事件ID}`，执行前替换 |
| 执行记录 | 执行人、目标主机、起止时间、耗时、返回码、完整输出，支持日志回放 |
| 超时与隔离 | 脚本超时强制终止；以最小权限运行 |

### 2.3 告警中心 `/sentinel/alerts`

| 区块 | 内容 |
| --- | --- |
| 告警规则 | 绑定哨兵监控项 → 触发条件（阈值 + 持续时长）→ 处置脚本 → 通知渠道 |
| 分级 | P0 紧急 / P1 高 / P2 中 / P3 低 |
| 通知渠道 | 站内消息、邮件、Webhook（企业微信/钉钉） |
| AI 研判 | 分析告警指标与日志，给出根因建议并**推荐**可用脚本；不代替人做决定 |
| 处置闭环 | 告警 → 通知 → **生成工单** → 预览 → **人工审批** → 执行 → 结果回填 → 人工确认关闭 |

### 2.4 闭环流程（与既有安全链对齐）

```
哨兵持续采集/监听
      ↓ 命中阈值（含持续时长防抖）
   产生告警（P0..P3）
      ↓
   告警联动模块：发通知 + AI 研判 + 推荐脚本
      ↓
   生成运维工单（状态 OPEN）
      ↓
   ┌─ 自动／人工发起处置 ─────────────┐
   │  MultiExec /preview → 审批 → /execute │  ← 复用既有链，P0/高危必须人工确认
   └──────────────────────────────┘
      ↓ 执行结果（返回码/输出/耗时）
   回填工单 → 结果验证 → 人工确认关闭 → 审计留痕
```

**为什么不做"告警直接执行"**：需求原文写的是"自动执行"，但本项目理念是受控执行。
因此实现为**「建议 + 待审批」**：低危（P2/P3）且脚本已发布、已授权时可由策略自动发起，
但仍要经过预览与审批闸门；**P0/P1 与高危脚本一律停等人工确认**。
这既满足闭环，又不破坏项目的可信执行定位 —— 而且这一点在竞赛答辩时是**加分项而非减分项**。

---

## 三、数据库表设计

沿用项目现有 SQL 风格（MySQL，`utf8mb4`，显式外键与索引）。
表名前缀 `sentinel_`，与既有业务表区分。**不改动既有表**。

```sql
-- 1) 哨兵任务：一个资产上的一个监控目标
CREATE TABLE sentinel_task (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  group_id        BIGINT       NULL,                    -- 资产分组，可空
  runtime_id      VARCHAR(128) NOT NULL,                -- 复用既有运行连接 ID
  name            VARCHAR(128) NOT NULL,
  kind            VARCHAR(24)  NOT NULL,                -- system | business | log
  target          VARCHAR(255) NOT NULL,                -- 指标名 / 端口 / URL / 日志路径
  match_rule      VARCHAR(255) NULL,                    -- 日志关键字，kind=log 时必填
  interval_sec    INT          NOT NULL DEFAULT 60,     -- 采集周期
  template_id     BIGINT       NULL,                    -- 阈值模板
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  last_seen_at    DATETIME     NULL,
  last_status     VARCHAR(16)  NULL,                    -- online | offline | error
  success_count   BIGINT       NOT NULL DEFAULT 0,
  failure_count   BIGINT       NOT NULL DEFAULT 0,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sentinel_task_user (user_id, enabled),
  KEY idx_sentinel_task_group (group_id),
  CONSTRAINT fk_sentinel_task_user FOREIGN KEY (user_id) REFERENCES app_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) 阈值模板（可复用、可批量下发）
CREATE TABLE sentinel_threshold_template (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  description     VARCHAR(500) NULL,
  rules_json      JSON         NOT NULL,   -- [{metric,op,value,for_sec}]，支持复合阈值（数组内全部满足）
  severity        VARCHAR(4)   NOT NULL DEFAULT 'P2',
  debounce_sec    INT          NOT NULL DEFAULT 300,  -- 持续时间防抖：瞬时峰值不告警
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sentinel_template_name (user_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3) 指标历史（时序；按保留策略清理）
CREATE TABLE sentinel_metric_sample (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  task_id         BIGINT       NOT NULL,
  sampled_at      DATETIME     NOT NULL,
  metric          VARCHAR(64)  NOT NULL,
  value_num       DOUBLE       NULL,
  value_text      VARCHAR(255) NULL,      -- 端口/进程存活等等价文本
  abnormal        TINYINT(1)   NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY idx_sample_task_time (task_id, sampled_at),
  CONSTRAINT fk_sample_task FOREIGN KEY (task_id) REFERENCES sentinel_task (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4) 脚本注册表（版本、标签、风险、语言）
CREATE TABLE sentinel_script (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  language        VARCHAR(16)  NOT NULL,   -- shell | python | bat | powershell
  description     VARCHAR(500) NULL,
  tags            VARCHAR(255) NULL,       -- 逗号分隔
  risk_level      VARCHAR(8)   NOT NULL DEFAULT 'MEDIUM',  -- LOW | MEDIUM | HIGH
  current_version INT          NOT NULL DEFAULT 1,
  approved        TINYINT(1)   NOT NULL DEFAULT 0,         -- 高危脚本需管理员审批后才可用
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  timeout_sec     INT          NOT NULL DEFAULT 60,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sentinel_script_name (user_id, name),
  KEY idx_sentinel_script_tags (tags)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5) 脚本版本（含语法预检与黑名单判定结果，便于回滚与追责）
CREATE TABLE sentinel_script_version (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  script_id       BIGINT       NOT NULL,
  version         INT          NOT NULL,
  body            MEDIUMTEXT   NOT NULL,
  parameters_json JSON         NULL,       -- [{name,required,default}]
  lint_status     VARCHAR(16)  NOT NULL,   -- ok | blocked | syntax_error
  lint_detail     VARCHAR(500) NULL,
  created_by      BIGINT       NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_script_version (script_id, version),
  CONSTRAINT fk_version_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6) 脚本执行记录（手动/定时/告警联动三种来源统一记录）
CREATE TABLE sentinel_script_run (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  script_id       BIGINT       NOT NULL,
  version         INT          NOT NULL,
  trigger_kind    VARCHAR(16)  NOT NULL,   -- manual | schedule | alert
  alert_id        BIGINT       NULL,       -- trigger_kind=alert 时回指告警
  run_id          VARCHAR(64)  NULL,       -- 关联既有操作运行记录 / TeamAgentRun
  actor_id        BIGINT       NULL,
  target_runtime  VARCHAR(128) NULL,
  variables_json  JSON         NULL,       -- 实际替换后的变量快照
  started_at      DATETIME     NOT NULL,
  finished_at     DATETIME     NULL,
  duration_ms     BIGINT       NULL,
  exit_code       INT          NULL,
  result          VARCHAR(16)  NOT NULL,   -- running | success | failed | timeout | rejected
  output_excerpt  TEXT         NULL,
  PRIMARY KEY (id),
  KEY idx_script_run_script (script_id, started_at),
  KEY idx_script_run_alert (alert_id),
  CONSTRAINT fk_run_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7) 告警规则（哨兵项 → 条件 → 处置脚本 → 通知渠道）
CREATE TABLE sentinel_alert_rule (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  template_id     BIGINT       NULL,
  severity        VARCHAR(4)   NOT NULL DEFAULT 'P2',
  script_id       BIGINT       NULL,       -- 推荐/绑定的处置脚本
  auto_dispatch   TINYINT(1)   NOT NULL DEFAULT 0,  -- 仅低危可置 1；仍走预览+审批
  notify_channels VARCHAR(255) NOT NULL DEFAULT 'inapp', -- 逗号分隔：inapp,email,webhook
  webhook_url     VARCHAR(500) NULL,
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_alert_rule_user (user_id, enabled),
  CONSTRAINT fk_rule_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8) 告警事件（工单主体；状态机即闭环）
CREATE TABLE sentinel_alert (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  rule_id         BIGINT       NULL,
  task_id         BIGINT       NULL,
  severity        VARCHAR(4)   NOT NULL,
  status          VARCHAR(16)  NOT NULL DEFAULT 'OPEN',
     -- OPEN → NOTIFIED → PENDING_APPROVAL → REMEDIATING → RESOLVED / CLOSED / SUPPRESSED
  title           VARCHAR(200) NOT NULL,
  metric          VARCHAR(64)  NULL,
  observed_value  VARCHAR(128) NULL,
  threshold_value VARCHAR(128) NULL,
  detail_json     JSON         NULL,       -- 采样上下文、日志命中片段
  ai_summary      TEXT         NULL,       -- AI 研判结论（标注为建议）
  recommended_script_id BIGINT NULL,
  ticket_id       BIGINT       NULL,       -- 关联工单（可复用既有运行记录作为工单）
  assignee_id     BIGINT       NULL,
  fired_at        DATETIME     NOT NULL,
  acknowledged_at DATETIME     NULL,
  resolved_at     DATETIME     NULL,
  closed_by       BIGINT       NULL,
  close_note      VARCHAR(500) NULL,
  PRIMARY KEY (id),
  KEY idx_alert_status (status, severity, fired_at),
  KEY idx_alert_task (task_id, fired_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9) 通知投递记录（区分"发出了"和"对方收到了"）
CREATE TABLE sentinel_notification (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  alert_id        BIGINT       NOT NULL,
  channel         VARCHAR(16)  NOT NULL,   -- inapp | email | webhook
  target          VARCHAR(255) NULL,
  status          VARCHAR(16)  NOT NULL,   -- pending | sent | failed
  attempts        INT          NOT NULL DEFAULT 0,
  error_detail    VARCHAR(500) NULL,
  sent_at         DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_notification_alert (alert_id),
  CONSTRAINT fk_notification_alert FOREIGN KEY (alert_id) REFERENCES sentinel_alert (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10) 告警处置时间线与审计（每次状态流转一条，不可修改）
CREATE TABLE sentinel_alert_event (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  alert_id        BIGINT       NOT NULL,
  at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_id        BIGINT       NULL,
  kind            VARCHAR(32)  NOT NULL,   -- FIRED | NOTIFIED | AI_ANALYZED | DISPATCH_REQUESTED | APPROVED | EXECUTED | RESULT_FILLED | CLOSED
  detail          VARCHAR(800) NULL,
  PRIMARY KEY (id),
  KEY idx_alert_event (alert_id, at),
  CONSTRAINT fk_event_alert FOREIGN KEY (alert_id) REFERENCES sentinel_alert (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

### 3.1 关键约束说明

- **不需要新建"工单表"**：既有 `operation_run` / `TeamAgentRun` 已经承载"谁在什么目标上执行了什么、结果如何"，
  `sentinel_alert.ticket_id` 指向它，避免两套工单语义。
- **复合阈值**用 `rules_json` 数组表达，数组内全部满足才触发；`debounce_sec` 是持续时间防抖，
  避免瞬时峰值误报（对应需求第 2 条）。
- **静默时段**（可扩展项）不建表，先做成告警规则上的一个时间窗字段即可，避免过早复杂化。
- **保留策略**：`sentinel_metric_sample` 需要按天清理（例如保留 30 天），
  清理任务复用既有 `ChatAttachmentRetention` 的调度写法，不引入新的调度框架。

---

## 四、多人协作（共享 Agent）优化方案

现状：`TeamAgentService` 支持草稿/发布，`TeamAgentRunService` 支持 `preview → approve → execute`，
`TeamNotificationService` / `TeamActivityService` 提供团队内通知与动态。基础齐全，但存在四个真实痛点。

### 优化点 1：把「审批」从一次性动作变成可追责的协作凭据 —— **已实现**

原实现 `approve` 只写 `approved_by`，事后只能回答"谁批的"，无法回答"基于什么批的"。

**做法**：`POST /api/team-agent-runs/{runId}/approve` 接受可选 `decisionBasis`，
存入 `team_agent_run.decision_basis`，并写入审计明细（`SUCCESS_BASIS:…`，超长截断到 200 字符）。

设计取舍：

- **依据是可选的**，不强制。强制填写会让人写 "ok" 来绕过，反而失去信息量；
- 空白依据规整为 `null`，避免存下一串空格冒充"有依据"；
- 列由 `TeamAgentRunConfig` **先探测再执行** `ALTER TABLE`（H2/MySQL 都没有通用的
  `ADD COLUMN IF NOT EXISTS`），因此重复启动与已手工加过列的库都不会失败；
- 兼容旧调用：保留 `approve(actor, runId)` 重载，既有前端不带 body 也不会 400。

### 优化点 2：并发协作的乐观锁与冲突提示 —— **已实现**

原实现 `saveDraft` 是"后写覆盖先写"：两人同时编辑同一 Agent 草稿时，
后保存的人会把前一个人的修改**静默抹掉**，前一个人还以为保存成功了。

**做法**：草稿带 `revision`（每次保存 +1），保存时可带 `expectedRevision` 比对。

- 不匹配时返回 **409**，文案说明"已被其他人修改（当前版本 N），请刷新后再保存"——
  而不是笼统的"参数错误"；
- `UPDATE` 语句**自带 revision 条件**（`WHERE id=? AND (? IS NULL OR revision=?)`），
  避免"检查通过后、更新之前被人插队"的竞态；
- 客户端声称在编辑一个不存在的草稿（`expectedRevision > 0` 但草稿不存在）也返回 409——
  这说明它读到的是过期状态；
- `expectedRevision` 可选：旧前端不带该字段时行为与改造前一致；
- 旧库没有 `revision` 列时读不到即返回 `null`，不做校验，不会让整个查询失败。

### 优化点 3：把「知识审核」接入协作闭环 —— **已实现**

`KnowledgeCandidateReviewView` 已经存在，但团队协作与知识沉淀是两条平行线。
**做法**：一次告警**人工关闭后**，可一键沉淀为**待审核的知识候选**
（故障现象 → 证据 → 研判 → 处置时间线 → 关闭说明），进入团队复核后进入知识库。

实现细节（为什么这样设计）：

- 只有 `CLOSED` 的告警允许沉淀，未关闭返回 **409** —— 避免把"还没验证过的处置"写成经验；
- 新表 `sentinel_knowledge_candidate`（`V20261012__sentinel_knowledge.sql`），状态 `PENDING_REVIEW`；
- 内容由服务端按固定模板生成，保证结构一致、可复盘，而不是让用户手写一段自由文本；
- 入口：`POST /api/sentinel/alerts/{id}/knowledge`，列表 `GET /api/sentinel/knowledge-candidates`。

### 优化点 4：共享 Agent 的「哨兵处置」专用工具入口 —— **已实现**

**做法**：在 `OperationToolService` 注册 `propose-remediation` 工具，**声明为非只读**，
因此 `TeamAgentRun` 会进入 `PENDING_APPROVAL`。它本身不渲染任何 shell 命令；
真正的命令来自哨兵脚本库，由 `SentinelScriptRunner.proposeRemediation()` 生成
`MultiExecService.preview()` 后交给人确认。

链路：`POST /api/sentinel/alerts/{id}/propose-remediation`
→ 校验告警与脚本 → 高危预检 → 变量校验与替换 → 生成 MultiExec 预览
→ `teamRuns.create()` 创建待审批运行 → 登记 `PENDING_APPROVAL` 执行记录。

之后仍是既有流程：团队审批人 `preview` → `approve` → 申请人 `consumeGrant` 执行。

**三道防回退的守卫**（都有测试）：

1. `SentinelScriptRunner` 里有 `multiExec.preview(` 但**没有** `multiExec.execute(`；
2. `OperationToolService.executeApprovedTeamRun` 遇到 `propose-remediation` 直接抛
   `TEAM_REMEDIATION_REQUIRES_SENTINEL_PREVIEW` —— 不允许从通用执行入口把它跑掉；
3. 返回文案明确写"哨兵不直接执行命令"，且不出现任何成功状态字段。

实测工具清单里它是 `readOnly=false, riskLevel=HIGH, requireConfirm=true`。

### AI 研判的实现方式（已实现，且刻意没有另造一套推理）

复用既有 `IncidentRecommendationService` + `OperatorMemoryService`：把告警的
指标/观测值/阈值翻译成它们认识的 `IncidentPattern`，让"既往运维经验"与"当前告警研判"
用**同一份记忆**，避免出现两套互相矛盾的建议。

`SentinelAdvisor` 的约束（都有测试钉住）：

- 推荐必须有**可解释理由**（命中脚本名称/标签的哪个词），不能只给一个分数；
- 候选脚本按风险升序排列 —— 顺序本身在表达"先试低危的"；
- P0/P1 或含 HIGH 风险候选时置 `humanFirst=true`；
- 无记忆、无候选时**如实说"需要人工判断"**，不编一个建议；
- 结论一律标注为**建议**，附证据与免责声明，且研判过程**不改变告警状态、不执行脚本**。

### 明确不做（避免破坏理念）

- 不做"告警直接执行脚本"的旁路；
- 不做无限权限的团队共享凭据；
- 不把 AI 研判结论写成既定事实，界面上一律标注为**建议**并给出证据来源。

---

## 五、实施顺序（建议）

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| P1 | 哨兵引擎（任务/采集/阈值/防抖/指标历史）+ 哨兵监控台 | **已实现**：`V20261011__sentinel.sql` 10 张表、`SentinelService`/`SentinelPoller`/`SentinelController`、`SentinelThreshold` 判定内核；界面 `/sentinel` |
| P2 | 脚本注册表 + 风险预检 + 执行记录（复用 MultiExec 执行） | **已实现**：注册表/版本/预检/三种触发模式统一编排（`SentinelScriptRunner`）、平台变量（`SentinelVariables`）、执行记录与回放、文件导入、定时计划。真正执行仍由既有 `/api/operations/multi-exec/execute` 完成 |
| P3 | 告警规则 + 告警中心 + 工单闭环 + 通知渠道 | **已实现**：规则、分级、状态机、待审批处置、结果回填、人工关闭；通知为逐渠道真实投递（站内写库、Webhook 真实 HTTP + SSRF 防护、邮件 SMTP 可配置且未配置时如实标 `not_configured`） |
| P4 | AI 研判接入 + 协作优化 1–4 | **已实现**：AI 研判（`SentinelAdvisor`）、通知（站内真实发出）、协作优化 1（审批决策依据）、2（草稿乐观锁）、3（告警→知识候选）、4（`propose-remediation` 受控工具）。邮件/Webhook 投递适配器待做 |

### 已实现的接口（与前端 `sentinelStore.js` 的 `SENTINEL_API` 一一对应）

```text
GET    /api/sentinel/tasks                    哨兵任务列表（含在线状态、采集成功率）
POST   /api/sentinel/tasks                    新建（白名单校验）
PATCH  /api/sentinel/tasks/{id}/enabled        启停
DELETE /api/sentinel/tasks/{id}
GET    /api/sentinel/tasks/{id}/samples        指标历史
GET    /api/sentinel/threshold-templates       阈值模板
POST   /api/sentinel/threshold-templates
GET    /api/sentinel/scripts / POST            脚本注册表（服务端预检必须通过才可保存）
GET    /api/sentinel/scripts/{id}/versions     版本
POST   /api/sentinel/scripts/{id}/versions     追加版本
GET    /api/sentinel/scripts/{id}/runs         执行记录
POST   /api/sentinel/scripts/lint              高危预检（只读预检，服务端才是把关人）
POST   /api/sentinel/scripts/{id}/prepare-run  三种触发模式统一入口：只生成预览 + 登记待审批
POST   /api/sentinel/runs/{runId}/result       回填真实执行结果
GET    /api/sentinel/variables                 平台变量清单（服务端为权威）
GET    /api/sentinel/alert-rules / POST        告警规则（P0/P1 强制 autoDispatch=false）
GET    /api/sentinel/alerts                    告警列表
POST   /api/sentinel/alerts/{id}/acknowledge
POST   /api/sentinel/alerts/{id}/dispatch      只进入 PENDING_APPROVAL，不执行脚本
POST   /api/sentinel/alerts/{id}/result        回填执行结果
POST   /api/sentinel/alerts/{id}/close         人工确认关闭
POST   /api/sentinel/alerts/{id}/analyze       AI 研判（只产出建议，不改状态、不执行）
POST   /api/sentinel/alerts/{id}/notify        通知（站内真实发出；邮件/Webhook 记 pending）
POST   /api/sentinel/alerts/{id}/knowledge     沉淀为知识候选（仅 CLOSED 告警，否则 409）
POST   /api/sentinel/alerts/{id}/propose-remediation  交给团队 Agent 提出处置（创建待审批运行）
GET    /api/sentinel/knowledge-candidates      知识候选列表
DELETE /api/sentinel/threshold-templates/{id}  删除（被引用时 409）
DELETE /api/sentinel/scripts/{id}              删除（被规则引用时 409）
DELETE /api/sentinel/alert-rules/{id}
GET    /api/sentinel/runtime-boundary          采集边界说明
```

## 脚本执行：三种模式，一条链，零旁路

需求里的「手动 / 定时 / 告警联动」三种触发模式，实现为**同一个准备入口**
`SentinelScriptRunner.prepare(...)`：无论谁来触发，都只做两件事 —— 生成既有
`MultiExecService.preview(...)` 的预览，并把这次意图登记为 `PENDING_APPROVAL`。

真正的执行必须由人带确认码提交既有 `/api/operations/multi-exec/execute`。

三条结构性约束由 `SentinelScriptRunnerPolicyTest` **直接读源码断言**：

1. runner 里出现 `multiExec.preview(` 但**不出现** `multiExec.execute(`；
2. 只有一个 `prepare` 入口，不存在"定时专用执行""告警专用执行"各自长出来；
3. 编排阶段只写 `PENDING_APPROVAL`，不会写成成功。

这类"读源码断言"的测试看起来粗暴，但它防的是最危险的回退：为了让定时模式"更顺手"
而在 runner 里直接调用执行接口——业务测试很难发现，这条断言会立刻失败。

### 定时执行：到点也不自动执行

定时计划保存在 `sentinel_script_schedule`，由 `SentinelPoller.fireSchedules()` 扫描到期项。
到点后它做的是**生成待审批预览**，不是执行命令。

**调度器默认关闭**（`smartops.sentinel.schedule.initial-delay-ms` 默认为极大值）。这是有意的：
定时触发属于"会自己发生"的行为，应该由部署方显式打开，而不是默认替人发起处置。
打开方式：

```yaml
smartops:
  sentinel:
    schedule:
      initial-delay-ms: 30000   # 启动 30 秒后开始检查
      interval-ms: 60000        # 每分钟检查一次到期计划
```

cron 只做 5 段形状校验（`SentinelVariables.validCron`），不宣称完整 cron 语义；
真正的到期判定基于 `next_fire_at <= NOW()`。
### 平台变量：精确替换，拒绝 shell 展开

`${主机IP}`、`${告警指标}`、`${告警值}` 等由 `SentinelVariables` 做**按名精确替换**，
不做 shell 展开。原因：这些值来自告警与资产信息，直接拼进 shell 会被命令替换利用。

- 未识别的变量**保持原样**并报出名字，不静默清空；
- 变量值含 `` ` ``、`$(...)`、换行、`; rm`、`| sh` 等控制字符时**直接拒绝**（400）；
- 前端 `PLATFORM_VARIABLES` 与服务端清单由测试比对，防止两侧漂移；
- 定时表达式只做 5 段形状校验，不宣称完整 cron 语义。

### 执行记录与回放

需求要求执行记录含"执行人 / 目标 / 耗时 / 返回码 / 完整日志与回放"。
`GET /api/sentinel/runs/{runId}` 返回一次执行的完整记录，界面在「执行记录与回放」面板展示。

**回放不是重新执行**：确认码从不落库（它只存在于 MultiExec 的预览里），
所以回放能看到"做了什么、结果如何"，看不到"怎么再跑一次"。界面文案明确写了这点。

空态也如实：没有记录就显示"这里只显示真实记录，不会为演示造数据"。

### 界面可创建性

初版界面只能**查看**任务/模板/规则，创建全靠直接调 API —— 那等于"模块有了但用不了"。
现在三个创建表单都补齐：

| 表单 | 位置 | 能配什么 |
| --- | --- | --- |
| 新建哨兵任务 | 监控台 | 名称、采集类别、目标、日志关键字、间隔、阈值模板、资产分组、运行连接 |
| 新建阈值模板 | 监控台 | 名称、级别、持续时间（防抖）、**多条规则即复合阈值** |
| 新建告警规则 | 告警中心 | 名称、阈值模板、级别、处置脚本、三种通知渠道、Webhook 地址、邮件收件人 |

**校验权威只在后端**：前端不复制指标白名单、端口范围、进程名规则，避免两份规则互相漂移。
前端只做最明显的空值提示，其余错误原样转达后端可读原因。

界面还提前说明"P0/P1 必须人工确认，不会自动发起"，而不是等提交后被服务端悄悄改成 false。

### 资产分组启停

需求要"资产分组启停"，原实现只能单个任务启停，多台机器要逐个点。

**做法**：在 `sentinel_task` 上加 `group_label`（自由文本，如 `web-prod` / `db-core`），
空值 = 未分组。`PATCH /api/sentinel/task-groups/{label}/enabled` 批量启停。

三个设计取舍：

- **不在既有 `server` 表上引入新分组实体**：哨兵任务本身已有"目标主机"语义，
  再建一层实体只增加同步负担，而且分组是运维标签、不是基础设施事实；
- 批量更新**必须带 `user_id` 条件**，否则会批量改到别人的任务（有测试断言）；
- 分组不存在时返回 `changed=0` 而不是报错 —— "这个分组现在没有任务"是正常状态。

### 脚本文件上传

`POST /api/sentinel/scripts/upload` 接受文件名 + 文本内容，按扩展名推断语言
（`.sh`/`.bash`→shell、`.py`→python、`.bat`/`.cmd`→bat、`.ps1`/`.psm1`→powershell）。

**关键约束：上传委托给 `createScript`，与手动编写走完全相同的预检与存储路径。**
因此不存在"上传能绕过高危预检"的缝隙——实测 `rm -rf /var/lib/mysql` 被拒。

其它边界：未知扩展名**拒绝而不是猜**（猜错语言会导致预检用错规则、执行用错解释器）；
含 NUL 字节视为二进制直接拒；超过 1 MiB 拒绝；`\r\n` 统一为 `\n`；
文件名只取最后一段，避免 `../` 进入名称。



### 通知投递：三种渠道的真实能力边界

`SentinelNotifier` 逐渠道投递并记录真实结果，**不把没发出去说成已发送**：

| 渠道 | 实现 | 状态码 |
| --- | --- | --- |
| 站内 | 复用既有 `TeamNotificationService`，真实写入 | `sent` |
| Webhook | 真实 HTTP POST（JDK HttpClient），带重试，受 SSRF 策略约束 | `sent` / `failed` / `rejected` |
| 邮件 | Jakarta Mail + Angus，**配置齐全才发信** | `sent` / `failed` / `not_configured` / `rejected` |

邮件渠道的配置（`smartops.sentinel.notify.email.*`）：`host`、`port`、`username`、
`password`、`from`、`starttls`、`timeout-ms`；收件人由告警规则上的 `email_to` 提供。

**判定规则**（`SentinelMailSetting.configured()`）：必须有 `host`、`from`、`port>0`，
且"有账号就必须有密码"。缺任一项即 `not_configured`，**不尝试发信** ——
宁可显示"没配"，也不能在没发出去的情况下写 `sent`。

为什么有账号没密码算"未配置"而不是"无认证"：否则会用空密码去认证，
得到一个含糊的认证失败，掩盖了真正的问题（配置没填完）。

安全取舍：开启 STARTTLS 但**保持证书校验**，不设置 `mail.smtp.ssl.trust` 全放行 ——
否则凭据可能发给伪装的服务器。

**Webhook 的 SSRF 防护**（`SentinelWebhookPolicy`）：URL 由用户填写、服务端主动请求，
不校验就等于把服务器变成内网探测器。策略是只允许 http/https，且解析出的**所有**地址
都不能是环回、私有、链路本地、组播或保留地址（含 `169.254.169.254` 云元数据）。

- 内网 WebHook（企业微信/钉钉内网网关）是真实需求，但**不默认放开**；
  需要时由部署方用 `smartops.sentinel.notify.webhook.allow-hosts` 显式列主机名；
- 校验发生在**保存规则时**，不是等告警触发才失败；
- 不重试的情况：地址被拒（`rejected`，`attempts=0`）与 4xx（对方明确拒绝）；
  5xx 与网络异常按 `max-attempts` 重试。

已知局限：这是"解析时校验"，无法阻止 DNS 重绑定。彻底解法是固定解析结果直连，
属残余风险，此处如实记录而非声称已完全解决。

### 采集边界（必须如实理解）

运行连接 `OperationRuntime` 是**用户会话级**资源，随会话关闭而释放。因此当前实现是
**会话内的常驻轮询**：连接在时按周期真实采集并落库；连接不在时任务标记为 `no_runtime`
并记录原因，**不伪造任何指标数据，也不产生告警**（空快照永远不命中阈值）。

要做到需求里写的 7×24 常驻采集，需要按需求原文部署**独立轻量采集器**，
由它上报到平台；这是架构演进项，不是把 `no_runtime` 换个显示文案就能解决的。

### 验证方式

```powershell
# 后端内核（阈值/防抖/高危预检/白名单注入防护/变量替换/执行链结构约束）
cd backend
mvn -B -o test -Dtest='Sentinel*Test'

# 告警闭环（真实 schema：H2 + 真实迁移脚本，覆盖研判/通知/沉淀/越权）
mvn -B -o test -Dtest='SentinelAlertWorkflowIntegrationTest'

# 协作优化：草稿乐观锁 + 审批决策依据
mvn -B -o test -Dtest='TeamAgentServiceTest,TeamAgentRunServiceTest'

# 接口契约与权限边界（真实后端）
cd ..\frontend
node test/sentinel-api-contract.browser.mjs
node test/sentinel-alert-workflow.browser.mjs
node test/sentinel-script-run.browser.mjs
```

### 本阶段的实测结论

- 12 张表在启动时由 `SentinelConfig` 幂等创建成功（含 `sentinel_knowledge_candidate`、
  `sentinel_script_schedule`，以及 `sentinel_task.group_label`、`team_agent_run.decision_basis`、
  `team_agent_version.revision` 三处加列）；
- 匿名访问哨兵接口被拒绝；
- 系统指标非白名单（`cpu; rm -rf /`）、进程名注入（`process:nginx; id`）、端口越界（`port:70000`）均被拒；
- 危险脚本在**保存时**即被拒（`rm -rf /var/lib/mysql` → 400），不是等到执行才拦；
- P0 规则的 `autoDispatch` 被服务端强制为 false，P3 才可能为 true；
- **脚本执行编排**（13/13）：未选目标 400、伪造运行连接被既有 registry 以 404 `RUNTIME_NOT_FOUND` 拒绝、
  变量缺失逐项列出、含命令替换的变量值被拒、非法触发模式被拒、未知脚本 404、高危脚本保存即拒、
  且没有任何伪造的 SUCCESS 执行记录；
- **界面**「发起执行（受控）」面板与「定时计划」面板均渲染正常，按钮文案为「生成预览（不执行）」，
  定时面板明确写"到点只生成待审批预览，不会自动执行命令"，0 页面错误；
- **定时计划**（10/10）：非法 cron 400、计划可创建/列出/删除、未知脚本 404、
  **且创建计划后没有产生任何执行记录**（证明"到点也不执行"）；
- **决策依据**（`TeamAgentRunServiceTest`）：带依据时落库并可读回、空白依据规整为 null、
  旧的无依据调用仍兼容；
- **迁移在真实 MySQL 生效**：`sentinel_script_schedule` 表、`team_agent_run.decision_basis` 列、
  `team_agent_version.revision` / `updated_at` 列均已存在；
- **协作优化 2**（草稿乐观锁）：旧 revision 保存返回 409 且内容未被覆盖、不带 revision 仍可保存、
  编辑不存在的草稿也返回 409；`UPDATE` 自带 revision 条件防插队；
- **执行记录回放**：未认证访问 `/api/sentinel/runs/{id}` 返回 401「请先登录」，
  不存在的记录返回 404；界面「执行记录与回放」面板渲染正常，
  空态如实写"不会为演示造数据"；
- **协作优化 4**：`propose-remediation` 在工具清单里是
  `readOnly=false, riskLevel=HIGH, requireConfirm=true`；未知告警返回 404。
  它只创建待审批运行，界面明写"不会执行命令"，0 页面错误；
- **通知投递**（实测）：内网 Webhook `http://127.0.0.1:8080/...` 在**保存规则时**即返回
  400「指向内网或保留地址（127.0.0.1），已拒绝」；公网地址可保存；投递结果逐渠道区分
  （`inapp=sent`、`email=not_configured`、内网 `webhook=rejected` 且 `attempts=0`）；
- **资产分组启停**（实测 11/11）：两个 `probe-web` 任务批量停用返回 `changed=2`，
  `probe-db` 分组不受影响，未知分组返回 `changed=0` 而非报错；
- **脚本上传**（实测）：`.py` 推断为 `python`；`.txt` 被拒并列出支持的扩展名；
  `rm -rf /var/lib/mysql` 上传时被预检拒绝——证明上传无法绕过预检；
- **界面可创建**（实测，0 页面错误）：从真实界面建出模板
  「UI探测模板」（2 条规则，CPU 使用率 > 90 且 内存使用率 > 90，复合阈值正确渲染）、
  哨兵「UI探测哨兵」、规则「UI探测规则」，三者随后均被清理（200）；
- **邮件渠道**：`SentinelMailSetting.configured()` 8 项单测覆盖
  （空配置、缺发件人、有账号无密码、端口 0 均判为未配置；自述信息不含密码；
  STARTTLS 不关闭证书校验）。因本机无 SMTP 服务器，**未做真实投递验证**，
  仅由集成测试断言未配置时返回 `not_configured`。
- 处置接口只把告警推进到 `PENDING_APPROVAL` 并返回"请走既有多机执行链路"，**没有执行脚本**；
- 轮询器真实运行：无运行连接的任务被标记 `no_runtime` 并累加失败次数，`samples` 为空、无告警产生；
- **研判**：返回建议 + 证据 + 候选脚本，落库 `ai_summary` 与 `recommended_script_id`，
  并断言**整个过程没有出现任何状态流转语句**；
- **沉淀**：未关闭告警返回 409 且不产生候选；已关闭告警生成的候选内容含现象/证据/研判/关闭说明；
- **通知**：`inapp` 记 `sent`，`email`/`webhook` 记 `pending`（没有投递适配器就不谎称已送达）；
- **越权**：他人告警一律 404，不泄露存在性。

### 本轮发现并修复的真实缺陷

**跨数据库主键读取**：`KeyHolder.getKey()` 在驱动返回多个生成列时（H2 会把带默认值的
`created_at` 一并返回）直接抛 `InvalidDataAccessApiUsageException`，导致创建接口 500。
已改为按列名取 `id`（`generatedId()`），MySQL 与 H2 行为一致。

**CSRF 轮换**：登录后 CSRF token 会轮换，用旧 token 发写请求会被 403 —— 这是保护机制在正常工作，
集成测试因此改为登录后重新获取 token。
