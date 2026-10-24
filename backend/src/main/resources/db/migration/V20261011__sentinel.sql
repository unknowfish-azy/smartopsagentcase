-- ============================================================
-- 哨兵监控 / 脚本执行 / 告警联动
-- ============================================================
-- 设计文档：docs/sentinel-scripts-alerts-design.md
--
-- 原则：
--   1. 不改动任何既有表；
--   2. 不新建"工单表"——既有 operation_run / team_agent_run 已承载
--      "谁在什么目标上执行了什么、结果如何"，告警表只保存 ticket_id 引用；
--   3. 脚本执行必须经既有预览/审批链，本迁移不提供任何直接执行通路。
-- 全部语句幂等，可由 ResourceDatabasePopulator 重复执行。

-- 1) 哨兵任务：一个资产上的一个监控目标
CREATE TABLE IF NOT EXISTS sentinel_task (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  runtime_id      VARCHAR(128) NULL,
  name            VARCHAR(128) NOT NULL,
  kind            VARCHAR(24)  NOT NULL,
  target          VARCHAR(255) NOT NULL,
  match_rule      VARCHAR(255) NULL,
  interval_sec    INT          NOT NULL DEFAULT 60,
  template_id     BIGINT       NULL,
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  last_seen_at    DATETIME     NULL,
  last_status     VARCHAR(16)  NULL,
  last_error      VARCHAR(500) NULL,
  success_count   BIGINT       NOT NULL DEFAULT 0,
  failure_count   BIGINT       NOT NULL DEFAULT 0,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sentinel_task_user (user_id, enabled),
  KEY idx_sentinel_task_runtime (runtime_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) 阈值模板（可复用、可批量下发）
CREATE TABLE IF NOT EXISTS sentinel_threshold_template (
  id            BIGINT       NOT NULL AUTO_INCREMENT,
  user_id       BIGINT       NOT NULL,
  name          VARCHAR(128) NOT NULL,
  description   VARCHAR(500) NULL,
  rules_json    JSON         NOT NULL,
  severity      VARCHAR(4)   NOT NULL DEFAULT 'P2',
  debounce_sec  INT          NOT NULL DEFAULT 300,
  created_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sentinel_template_name (user_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3) 指标历史（时序）
CREATE TABLE IF NOT EXISTS sentinel_metric_sample (
  id          BIGINT       NOT NULL AUTO_INCREMENT,
  task_id     BIGINT       NOT NULL,
  sampled_at  DATETIME     NOT NULL,
  metric      VARCHAR(64)  NOT NULL,
  value_num   DOUBLE       NULL,
  value_text  VARCHAR(255) NULL,
  abnormal    TINYINT(1)   NOT NULL DEFAULT 0,
  PRIMARY KEY (id),
  KEY idx_sample_task_time (task_id, sampled_at),
  CONSTRAINT fk_sample_task FOREIGN KEY (task_id) REFERENCES sentinel_task (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4) 脚本注册表
CREATE TABLE IF NOT EXISTS sentinel_script (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  language        VARCHAR(16)  NOT NULL,
  description     VARCHAR(500) NULL,
  tags            VARCHAR(255) NULL,
  risk_level      VARCHAR(8)   NOT NULL DEFAULT 'LOW',
  current_version INT          NOT NULL DEFAULT 1,
  approved        TINYINT(1)   NOT NULL DEFAULT 0,
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  timeout_sec     INT          NOT NULL DEFAULT 60,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_sentinel_script_name (user_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5) 脚本版本（含预检结论，便于回滚与追责）
CREATE TABLE IF NOT EXISTS sentinel_script_version (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  script_id       BIGINT       NOT NULL,
  version         INT          NOT NULL,
  body            MEDIUMTEXT   NOT NULL,
  parameters_json JSON         NULL,
  lint_status     VARCHAR(16)  NOT NULL,
  lint_detail     VARCHAR(500) NULL,
  created_by      BIGINT       NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_script_version (script_id, version),
  CONSTRAINT fk_version_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6) 脚本执行记录（手动 / 定时 / 告警联动统一记录）
CREATE TABLE IF NOT EXISTS sentinel_script_run (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  script_id       BIGINT       NOT NULL,
  version         INT          NOT NULL,
  trigger_kind    VARCHAR(16)  NOT NULL,
  alert_id        BIGINT       NULL,
  run_id          VARCHAR(64)  NULL,
  actor_id        BIGINT       NULL,
  target_runtime  VARCHAR(128) NULL,
  variables_json  JSON         NULL,
  started_at      DATETIME     NOT NULL,
  finished_at     DATETIME     NULL,
  duration_ms     BIGINT       NULL,
  exit_code       INT          NULL,
  result          VARCHAR(16)  NOT NULL,
  output_excerpt  TEXT         NULL,
  PRIMARY KEY (id),
  KEY idx_script_run_script (script_id, started_at),
  KEY idx_script_run_alert (alert_id),
  CONSTRAINT fk_run_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7) 告警规则（哨兵项 → 条件 → 处置脚本 → 通知渠道）
CREATE TABLE IF NOT EXISTS sentinel_alert_rule (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  template_id     BIGINT       NULL,
  severity        VARCHAR(4)   NOT NULL DEFAULT 'P2',
  script_id       BIGINT       NULL,
  auto_dispatch   TINYINT(1)   NOT NULL DEFAULT 0,
  notify_channels VARCHAR(255) NOT NULL DEFAULT 'inapp',
  webhook_url     VARCHAR(500) NULL,
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_alert_rule_user (user_id, enabled),
  CONSTRAINT fk_rule_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8) 告警事件（工单主体；status 即闭环状态机）
CREATE TABLE IF NOT EXISTS sentinel_alert (
  id                    BIGINT       NOT NULL AUTO_INCREMENT,
  rule_id               BIGINT       NULL,
  task_id               BIGINT       NULL,
  severity              VARCHAR(4)   NOT NULL,
  status                VARCHAR(16)  NOT NULL DEFAULT 'OPEN',
  title                 VARCHAR(200) NOT NULL,
  metric                VARCHAR(64)  NULL,
  observed_value        VARCHAR(128) NULL,
  threshold_value       VARCHAR(128) NULL,
  detail_json           JSON         NULL,
  ai_summary            TEXT         NULL,
  recommended_script_id BIGINT       NULL,
  ticket_id             BIGINT       NULL,
  assignee_id           BIGINT       NULL,
  fired_at              DATETIME     NOT NULL,
  acknowledged_at       DATETIME     NULL,
  resolved_at           DATETIME     NULL,
  closed_by             BIGINT       NULL,
  close_note            VARCHAR(500) NULL,
  PRIMARY KEY (id),
  KEY idx_alert_status (status, severity, fired_at),
  KEY idx_alert_task (task_id, fired_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9) 通知投递记录（区分"已发送"与"对方已收到"）
CREATE TABLE IF NOT EXISTS sentinel_notification (
  id           BIGINT       NOT NULL AUTO_INCREMENT,
  alert_id     BIGINT       NOT NULL,
  channel      VARCHAR(16)  NOT NULL,
  target       VARCHAR(255) NULL,
  status       VARCHAR(16)  NOT NULL,
  attempts     INT          NOT NULL DEFAULT 0,
  error_detail VARCHAR(500) NULL,
  sent_at      DATETIME     NULL,
  PRIMARY KEY (id),
  KEY idx_notification_alert (alert_id),
  CONSTRAINT fk_notification_alert FOREIGN KEY (alert_id) REFERENCES sentinel_alert (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10) 告警处置时间线（每次状态流转一条，不可修改）
CREATE TABLE IF NOT EXISTS sentinel_alert_event (
  id       BIGINT       NOT NULL AUTO_INCREMENT,
  alert_id BIGINT       NOT NULL,
  at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  actor_id BIGINT       NULL,
  kind     VARCHAR(32)  NOT NULL,
  detail   VARCHAR(800) NULL,
  PRIMARY KEY (id),
  KEY idx_alert_event (alert_id, at),
  CONSTRAINT fk_event_alert FOREIGN KEY (alert_id) REFERENCES sentinel_alert (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
