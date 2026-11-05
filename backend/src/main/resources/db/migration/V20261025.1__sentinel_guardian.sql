-- 哨兵守护 Agent：告警自动取证 + 指标基线学习
CREATE TABLE IF NOT EXISTS sentinel_guardian_evidence (
  id         BIGINT       NOT NULL AUTO_INCREMENT,
  user_id    BIGINT       NOT NULL,
  alert_id   BIGINT       NOT NULL,
  kind       VARCHAR(32)  NOT NULL,
  title      VARCHAR(255) NOT NULL,
  detail     VARCHAR(800) NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_guardian_evidence_user (user_id, created_at),
  KEY idx_guardian_evidence_alert (alert_id, kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS sentinel_learning_profile (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  user_id             BIGINT       NOT NULL,
  task_id             BIGINT       NOT NULL,
  task_name           VARCHAR(128) NULL,
  metric              VARCHAR(64)  NOT NULL,
  operator            VARCHAR(8)   NULL,
  sample_count        INT          NOT NULL DEFAULT 0,
  avg_value           DOUBLE       NULL,
  p95_value           DOUBLE       NULL,
  min_value           DOUBLE       NULL,
  max_value           DOUBLE       NULL,
  current_threshold   DOUBLE       NULL,
  suggested_threshold DOUBLE       NULL,
  status              VARCHAR(16)  NOT NULL DEFAULT 'SUGGESTED',
  learned_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  applied_at          DATETIME     NULL,
  updated_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_learning_task_metric (user_id, task_id, metric)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
