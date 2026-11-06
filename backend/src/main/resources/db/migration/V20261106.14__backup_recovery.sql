-- ============================================================
-- OPS-13：备份恢复集合、制品清单、异机副本与隔离恢复演练
-- ============================================================
-- 原则：
--   1. 恢复集合按组件登记（数据库 / 附件 / 知识 manifest / 审计 / 密钥），缺组件如实标 INCOMPLETE；
--   2. 制品清单只存 sha256、字节数、条目数与来源，不存凭据与密钥内容；
--   3. 校验结果、异机副本、保留期分别记录，不用"备份任务退出码 0"代替"可恢复"；
--   4. RPO/RTO 由演练的真实时间戳计算（基线采集时间 → 演练开始 → 演练结束），不接受调用方自报。
-- 全部语句幂等。

CREATE TABLE IF NOT EXISTS backup_recovery_set (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  environment     VARCHAR(64)  NOT NULL,
  components      VARCHAR(255) NOT NULL,
  retention_days  INT          NOT NULL DEFAULT 14,
  offsite_required TINYINT(1)  NOT NULL DEFAULT 1,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_backup_set_name (user_id, name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS backup_artifact_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  set_id              BIGINT       NOT NULL,
  artifact_id         VARCHAR(200) NOT NULL,
  component           VARCHAR(32)  NOT NULL,
  source_uri          VARCHAR(500) NULL,
  sha256              VARCHAR(64)  NOT NULL,
  bytes               BIGINT       NOT NULL,
  item_count          BIGINT       NOT NULL,
  captured_at         DATETIME     NOT NULL,
  retention_until     DATETIME     NULL,
  offsite_location    VARCHAR(500) NULL,
  offsite_verified_at DATETIME     NULL,
  verification_status VARCHAR(24)  NOT NULL DEFAULT 'UNVERIFIED',
  verified_at         DATETIME     NULL,
  verification_detail VARCHAR(800) NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_backup_artifact (set_id, artifact_id),
  KEY idx_backup_artifact_component (set_id, component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS backup_drill_record (
  id                   BIGINT       NOT NULL AUTO_INCREMENT,
  set_id               BIGINT       NOT NULL,
  mode                 VARCHAR(32)  NOT NULL,
  started_at           DATETIME     NOT NULL,
  finished_at          DATETIME     NOT NULL,
  baseline_captured_at DATETIME     NULL,
  rpo_seconds          BIGINT       NULL,
  rto_seconds          BIGINT       NULL,
  expected_count       BIGINT       NOT NULL,
  restored_count       BIGINT       NOT NULL,
  hash_verified        TINYINT(1)   NOT NULL,
  reference_check      VARCHAR(16)  NOT NULL,
  key_query_check      VARCHAR(16)  NOT NULL,
  result               VARCHAR(24)  NOT NULL,
  detail_json          TEXT         NULL,
  created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_backup_drill_set (set_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
