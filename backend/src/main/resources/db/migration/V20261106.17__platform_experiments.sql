-- ============================================================
-- OPS-16：多集群 / 边缘 / 故障演练的可退出评估
-- ============================================================
-- 原则：
--   1. 引入前必须把必要性、业务触发条件、额外控制面、权限、兼容性、开销与卸载步骤写清楚；
--   2. 演练必须先声明停止条件；停止触发却没留证据判 FAILED，缺恢复证据判 UNVERIFIED；
--   3. 恢复证据可以引用 OPS-13 已验证的备份演练，不另建一套恢复验证；
--   4. 只有"有 VERIFIED 演练 + 卸载已留证"才允许判定为可引入（canAdopt）；
--   5. 本表只登记评估事实，不替代既有 Run / 审批 / 审计体系。
-- 全部语句幂等。

CREATE TABLE IF NOT EXISTS platform_experiment_evaluation (
  id               BIGINT       NOT NULL AUTO_INCREMENT,
  user_id          BIGINT       NOT NULL,
  component        VARCHAR(32)  NOT NULL,
  title            VARCHAR(200) NOT NULL,
  necessity        TEXT         NOT NULL,
  business_trigger TEXT         NOT NULL,
  control_plane    TEXT         NOT NULL,
  permissions      TEXT         NOT NULL,
  compatibility    TEXT         NOT NULL,
  cost_note        TEXT         NOT NULL,
  uninstall_steps  TEXT         NOT NULL,
  exit_verified_at DATETIME     NULL,
  exit_evidence    VARCHAR(512) NULL,
  created_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_experiment_component (user_id, component)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS platform_experiment_drill (
  id                BIGINT       NOT NULL AUTO_INCREMENT,
  user_id           BIGINT       NOT NULL,
  evaluation_id     BIGINT       NOT NULL,
  mode              VARCHAR(32)  NOT NULL,
  scope             VARCHAR(200) NOT NULL,
  started_at        DATETIME     NOT NULL,
  finished_at       DATETIME     NOT NULL,
  stop_conditions   TEXT         NOT NULL,
  stop_triggered    TINYINT(1)   NOT NULL,
  stop_evidence     VARCHAR(512) NULL,
  recovery_evidence VARCHAR(512) NULL,
  backup_drill_id   BIGINT       NULL,
  result            VARCHAR(24)  NOT NULL,
  gaps_json         TEXT         NULL,
  created_at        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_experiment_drill (user_id, evaluation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
