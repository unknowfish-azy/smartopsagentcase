-- ============================================================
-- OPS-12：IaC / GitOps 计划、下发、验证、发布历史
-- ============================================================
-- 原则：
--   1. 不新建第二套审批 / Run 权威：apply 必须引用既有 operation_run_record 的 trace_id 作为执行证据；
--   2. plan 只存脱敏摘要（地址 / 类型 / 动作），不存 before/after 值，避免密钥随计划落库；
--   3. SENT（已下发）与 APPLIED（执行成功）、VERIFIED（变更后验证通过）分开记录；
--   4. 同一 workspace 同时只允许一个 DISPATCHED 的记录（状态锁），防止并发变更；
--   5. 发布历史记录 commit 与镜像 digest，用于期望/实际漂移分析与受控回滚。
-- 全部语句幂等。

CREATE TABLE IF NOT EXISTS iac_plan_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  user_id             BIGINT       NOT NULL,
  workspace           VARCHAR(200) NOT NULL,
  environment         VARCHAR(64)  NOT NULL,
  plan_digest         VARCHAR(80)  NOT NULL,
  plan_summary_json   TEXT         NOT NULL,
  create_count        INT          NOT NULL DEFAULT 0,
  update_count        INT          NOT NULL DEFAULT 0,
  delete_count        INT          NOT NULL DEFAULT 0,
  replace_count       INT          NOT NULL DEFAULT 0,
  change_count        INT          NOT NULL DEFAULT 0,
  truncated           TINYINT(1)   NOT NULL DEFAULT 0,
  destroy_detected    TINYINT(1)   NOT NULL DEFAULT 0,
  terraform_version   VARCHAR(64)  NULL,
  state_serial        BIGINT       NULL,
  state_lineage       VARCHAR(128) NULL,
  commit_sha          VARCHAR(64)  NULL,
  image_digest        VARCHAR(160) NULL,
  release_version     VARCHAR(64)  NULL,
  rollback_of_release_id BIGINT    NULL,
  status              VARCHAR(24)  NOT NULL,
  approval_nonce      VARCHAR(96)  NULL,
  approved_by         BIGINT       NULL,
  approved_at         DATETIME     NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_iac_plan_digest (user_id, workspace, plan_digest),
  KEY idx_iac_plan_workspace (user_id, workspace, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS iac_apply_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  plan_id             BIGINT       NOT NULL,
  user_id             BIGINT       NOT NULL,
  workspace           VARCHAR(200) NOT NULL,
  status              VARCHAR(24)  NOT NULL,
  dispatch_status     VARCHAR(16)  NOT NULL,
  dispatched_at       DATETIME     NOT NULL,
  run_trace_id        VARCHAR(64)  NULL,
  exit_code           INT          NULL,
  applied_at          DATETIME     NULL,
  verification_status VARCHAR(24)  NOT NULL DEFAULT 'UNVERIFIED',
  verified_at         DATETIME     NULL,
  verification_detail TEXT         NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_iac_apply_plan (plan_id),
  KEY idx_iac_apply_workspace (user_id, workspace, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS iac_release_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  user_id             BIGINT       NOT NULL,
  workspace           VARCHAR(200) NOT NULL,
  environment         VARCHAR(64)  NOT NULL,
  release_version     VARCHAR(64)  NOT NULL,
  commit_sha          VARCHAR(64)  NULL,
  image_digest        VARCHAR(160) NULL,
  plan_id             BIGINT       NOT NULL,
  apply_id            BIGINT       NOT NULL,
  direction           VARCHAR(16)  NOT NULL,
  status              VARCHAR(24)  NOT NULL,
  applied_at          DATETIME     NOT NULL,
  verified_at         DATETIME     NULL,
  previous_release_id BIGINT       NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_iac_release_workspace (user_id, workspace, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
