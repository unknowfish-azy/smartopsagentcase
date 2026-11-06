-- ============================================================
-- P0-04 Runbook 与自动化作业
-- ============================================================
-- 设计目标：把"脚本 / 命令"升级成**可治理的作业**：
--   名称/版本/作者/适用环境、输入参数 Schema、前置检查 → 执行 → 后置检查、
--   风险等级与审批、目标选择器与目标快照、超时/重试/取消/失败分支、
--   并发上限/批次/金丝雀、回滚步骤与幂等规则、每目标独立结果、定时与事件触发。
--
-- 复用的既有能力（本迁移不重复建设）：
--   1. 执行与证据：operation_run_record / operation_run_output / operation_run_evidence
--      —— 每个目标每次尝试写一条 Run，由 OperationRunRecorder 授权写入；
--   2. 风险与审批口径：OperationRiskPolicy 的风险分级与所需确认次数；
--   3. 目标归属：OperationRuntimeRegistry 校验运行连接是否属于当前用户；
--   4. 告警事实：sentinel_alert 只读引用，事件触发不新建告警表。
--
-- 状态机（runbook_run.status）：
--   AWAITING_TARGETS -> PENDING_APPROVAL -> APPROVED -> RUNNING
--     -> SUCCEEDED / PARTIAL / FAILED / UNKNOWN / CANCELLED
--     -> ROLLING_BACK -> ROLLED_BACK / ROLLBACK_FAILED
--   失败分支：FAILED/PARTIAL/UNKNOWN 可人工触发 ROLLING_BACK；
--   未知状态：命令已派发但结果不可确认 -> UNKNOWN，禁止自动重试写操作。
-- 全部语句幂等，可由 Flyway / ResourceDatabasePopulator 重复执行。

-- 1) Runbook 定义（名称、说明、适用环境、作者、风险基线）
CREATE TABLE IF NOT EXISTS runbook (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  description     VARCHAR(500) NULL,
  environment     VARCHAR(16)  NOT NULL DEFAULT 'DEV',
  owner_id        BIGINT       NULL,
  declared_risk   VARCHAR(8)   NOT NULL DEFAULT 'LOW',
  enabled         TINYINT(1)   NOT NULL DEFAULT 1,
  current_version INT          NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_runbook_user_name (user_id, name),
  KEY idx_runbook_user (user_id, enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2) Runbook 版本（不可变快照：参数 Schema、选择器、限制、风险与幂等规则）
CREATE TABLE IF NOT EXISTS runbook_version (
  id                 BIGINT       NOT NULL AUTO_INCREMENT,
  runbook_id         BIGINT       NOT NULL,
  version            INT          NOT NULL,
  note               VARCHAR(500) NULL,
  risk_level         VARCHAR(8)   NOT NULL DEFAULT 'LOW',
  parameters_json    TEXT         NULL,
  selector_json      TEXT         NULL,
  timeout_sec        INT          NOT NULL DEFAULT 300,
  retry_limit        INT          NOT NULL DEFAULT 0,
  concurrency_limit  INT          NOT NULL DEFAULT 1,
  batch_size         INT          NOT NULL DEFAULT 10,
  canary_size        INT          NOT NULL DEFAULT 0,
  idempotency_rule   VARCHAR(500) NULL,
  created_by         BIGINT       NULL,
  created_at         DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_runbook_version (runbook_id, version),
  CONSTRAINT fk_runbook_version_runbook FOREIGN KEY (runbook_id) REFERENCES runbook (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3) 作业步骤：前置检查 / 执行 / 后置检查 / 回滚
CREATE TABLE IF NOT EXISTS runbook_step (
  id               BIGINT       NOT NULL AUTO_INCREMENT,
  version_id       BIGINT       NOT NULL,
  phase            VARCHAR(16)  NOT NULL,
  seq              INT          NOT NULL,
  name             VARCHAR(128) NOT NULL,
  body             TEXT         NOT NULL,
  expect_exit_code INT          NOT NULL DEFAULT 0,
  on_failure       VARCHAR(16)  NOT NULL DEFAULT 'ABORT',
  timeout_sec      INT          NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_runbook_step (version_id, phase, seq),
  CONSTRAINT fk_runbook_step_version FOREIGN KEY (version_id) REFERENCES runbook_version (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4) 作业运行（审批对象 = 版本 + 参数 + 目标快照 + 内容哈希）
CREATE TABLE IF NOT EXISTS runbook_run (
  id                 BIGINT        NOT NULL AUTO_INCREMENT,
  runbook_id         BIGINT        NOT NULL,
  version_id         BIGINT        NOT NULL,
  version            INT           NOT NULL,
  user_id            BIGINT        NOT NULL,
  environment        VARCHAR(16)   NOT NULL,
  trigger_kind       VARCHAR(16)   NOT NULL,
  trigger_ref        VARCHAR(160)  NULL,
  idempotency_key    VARCHAR(160)  NULL,
  status             VARCHAR(24)   NOT NULL,
  parameters_json    TEXT          NULL,
  target_selector_json TEXT        NULL,
  target_snapshot_json TEXT        NULL,
  content_hash       VARCHAR(64)   NOT NULL,
  risk_level         VARCHAR(8)    NOT NULL,
  required_approvals INT           NOT NULL DEFAULT 0,
  approval_count     INT           NOT NULL DEFAULT 0,
  approved_by        BIGINT        NULL,
  second_approver_id BIGINT        NULL,
  approved_at        DATETIME      NULL,
  nonce_hash         VARCHAR(64)   NULL,
  cancel_requested   TINYINT(1)    NOT NULL DEFAULT 0,
  total_targets      INT           NOT NULL DEFAULT 0,
  succeeded_count    INT           NOT NULL DEFAULT 0,
  failed_count       INT           NOT NULL DEFAULT 0,
  unknown_count      INT           NOT NULL DEFAULT 0,
  cancelled_count    INT           NOT NULL DEFAULT 0,
  skipped_count      INT           NOT NULL DEFAULT 0,
  note               VARCHAR(500)  NULL,
  created_at         DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at         DATETIME      NULL,
  finished_at        DATETIME      NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_runbook_run_idempotency (user_id, idempotency_key),
  KEY idx_runbook_run_status (status, created_at),
  KEY idx_runbook_run_runbook (runbook_id, created_at),
  CONSTRAINT fk_runbook_run_runbook FOREIGN KEY (runbook_id) REFERENCES runbook (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5) 每目标独立结果（部分成功 / 失败 / 未知分别可见）
CREATE TABLE IF NOT EXISTS runbook_run_target (
  id                BIGINT       NOT NULL AUTO_INCREMENT,
  run_id            BIGINT       NOT NULL,
  runtime_id        VARCHAR(128) NOT NULL,
  target_label      VARCHAR(160) NULL,
  batch_no          INT          NOT NULL DEFAULT 1,
  canary            TINYINT(1)   NOT NULL DEFAULT 0,
  status            VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
  attempt           INT          NOT NULL DEFAULT 0,
  operation_run_id  BIGINT       NULL,
  exit_code         INT          NULL,
  output_excerpt    TEXT         NULL,
  error             VARCHAR(500) NULL,
  pre_check_status  VARCHAR(16)  NULL,
  post_check_status VARCHAR(16)  NULL,
  rollback_status   VARCHAR(16)  NULL,
  rollback_output   TEXT         NULL,
  started_at        DATETIME     NULL,
  finished_at       DATETIME     NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_runbook_run_target (run_id, runtime_id),
  KEY idx_runbook_target_status (run_id, status),
  CONSTRAINT fk_runbook_target_run FOREIGN KEY (run_id) REFERENCES runbook_run (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6) 定时执行（到点只生成待绑定目标的作业，不凭空执行）
CREATE TABLE IF NOT EXISTS runbook_schedule (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  runbook_id   BIGINT      NOT NULL,
  user_id      BIGINT      NOT NULL,
  cron_expr    VARCHAR(64) NOT NULL,
  environment  VARCHAR(16) NOT NULL DEFAULT 'DEV',
  enabled      TINYINT(1)  NOT NULL DEFAULT 1,
  last_fire_at DATETIME    NULL,
  next_fire_at DATETIME    NULL,
  created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_runbook_schedule_due (enabled, next_fire_at),
  CONSTRAINT fk_runbook_schedule_runbook FOREIGN KEY (runbook_id) REFERENCES runbook (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7) 事件触发（告警 → 作业；同一告警对同一 Runbook 只生成一次）
CREATE TABLE IF NOT EXISTS runbook_trigger (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  runbook_id   BIGINT      NOT NULL,
  user_id      BIGINT      NOT NULL,
  event_type   VARCHAR(24) NOT NULL DEFAULT 'ALERT',
  min_severity VARCHAR(4)  NOT NULL DEFAULT 'P1',
  enabled      TINYINT(1)  NOT NULL DEFAULT 1,
  created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_runbook_trigger (runbook_id, event_type),
  CONSTRAINT fk_runbook_trigger_runbook FOREIGN KEY (runbook_id) REFERENCES runbook (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
