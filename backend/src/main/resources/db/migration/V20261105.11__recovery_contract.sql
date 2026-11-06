-- ============================================================
-- 恢复契约 v1 持久化（Recovery Contract v1 persistence）
-- ============================================================
-- 依据：docs/design/recovery-contract-v1/platform-integration.md（N06 平台接入映射）
--
-- 设计原则：
--   1. 不新建第二套 Run / 审批 / 审计权威；契约通过 run_id 引用既有 operation_run_record。
--   2. 契约、回执、观测、回放包各自落表，恢复判定与纠察轴（inspection_verification）分开存。
--   3. 契约与回执正文以 canonical JSON 原样保存（contract_json / receipt_json），
--      冗余列只用于查询、过滤与唯一约束，不参与改写正文。
--   4. 时间字段以 UTC ISO-8601 字符串保存（semantics §4.1），避免跨库时区与精度漂移；
--      ISO 字符串字典序与时间序一致，可直接用于排序。
--   5. 非 VERIFIED 的回执必须 receipt_state='NOT_ISSUED' 且 issued_at/valid_until 为 null，
--      该约束在服务层强制（跨库 CHECK 支持不一致，不依赖 DDL）。
-- 全部语句幂等，可由 Flyway / ResourceDatabasePopulator 重复执行。
-- 回滚：DROP TABLE recovery_replay_bundle_record, recovery_receipt_record,
--       recovery_observation_record, recovery_contract_record（仅新增表，不影响既有数据）。

-- 1) 恢复契约主表
CREATE TABLE IF NOT EXISTS recovery_contract_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  contract_id         VARCHAR(128) NOT NULL,
  contract_version    VARCHAR(32)  NOT NULL,
  run_id              BIGINT       NOT NULL,
  owner_user_id       BIGINT       NOT NULL,
  idempotency_key     VARCHAR(128) NOT NULL,
  scope               VARCHAR(200) NOT NULL,
  target_id           VARCHAR(200) NOT NULL,
  target_kind          VARCHAR(32)  NULL,
  expected_revision   VARCHAR(64)  NOT NULL,
  digest              VARCHAR(80)  NOT NULL,
  contract_json       TEXT         NOT NULL,
  claim_json          TEXT         NOT NULL,
  expires_after_ms    BIGINT       NOT NULL,
  valid_from          VARCHAR(40)  NOT NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  -- 同一主体 + 同一幂等键只允许一条契约，重复创建走 409 而非重复签发
  UNIQUE KEY uk_recovery_contract_idem (owner_user_id, idempotency_key),
  UNIQUE KEY uk_recovery_contract_digest (owner_user_id, digest),
  KEY idx_recovery_contract_run (run_id),
  KEY idx_recovery_contract_owner (owner_user_id, created_at)
);

-- 2) 证据观测表（由 Python 探针经内部 token 写入；原始 payload 不进 run-event）
CREATE TABLE IF NOT EXISTS recovery_observation_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  contract_record_id BIGINT       NOT NULL,
  observation_id      VARCHAR(128) NOT NULL,
  run_id              VARCHAR(128) NULL,
  verification_round  INT          NULL,
  collector_id        VARCHAR(64)  NOT NULL,
  probe_id            VARCHAR(64)  NOT NULL,
  source_group        VARCHAR(64)  NOT NULL,
  observed_at         VARCHAR(40)  NOT NULL,
  binding_revision    VARCHAR(64)  NOT NULL,
  observed_revision   VARCHAR(64)  NULL,
  sequence            INT          NOT NULL,
  elapsed_ms          INT          NULL,
  payload_json        TEXT         NULL,
  error_text          TEXT         NULL,
  artifact_digest     VARCHAR(80)  NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  -- 同一契约内观测 ID 唯一：重复 ID 不填补采样槽（semantics §3.1）
  UNIQUE KEY uk_recovery_observation (contract_record_id, observation_id),
  KEY idx_recovery_observation_probe (contract_record_id, probe_id, sequence)
);

-- 3) 核验回执表
CREATE TABLE IF NOT EXISTS recovery_receipt_record (
  id                      BIGINT       NOT NULL AUTO_INCREMENT,
  contract_record_id      BIGINT       NOT NULL,
  receipt_id              VARCHAR(128) NOT NULL,
  run_id                  VARCHAR(128) NOT NULL,
  verification_round      INT          NOT NULL,
  verdict                 VARCHAR(24)  NOT NULL,
  receipt_state           VARCHAR(24)  NOT NULL,
  issued_at                VARCHAR(40)  NULL,
  valid_until              VARCHAR(40)  NULL,
  evidence_snapshot_digest VARCHAR(80) NULL,
  policy_version          VARCHAR(64)  NOT NULL,
  receipt_json            TEXT         NOT NULL,
  obligation_results_json TEXT         NOT NULL,
  probe_decision_json     TEXT         NULL,
  invalidation_events_json TEXT        NULL,
  created_at              DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_recovery_receipt (contract_record_id, receipt_id),
  KEY idx_recovery_receipt_state (contract_record_id, receipt_state)
);

-- 4) 回放包表（冻结输入 + 回放结果；变形包必须保留 parent 与 mutation_diff）
CREATE TABLE IF NOT EXISTS recovery_replay_bundle_record (
  id                  BIGINT       NOT NULL AUTO_INCREMENT,
  contract_record_id BIGINT       NOT NULL,
  bundle_id           VARCHAR(128) NOT NULL,
  parent_bundle_id    VARCHAR(128) NULL,
  is_historical_fact  TINYINT(1)   NOT NULL DEFAULT 1,
  bundle_digest       VARCHAR(80)  NOT NULL,
  bundle_json         TEXT         NOT NULL,
  replay_result_json  TEXT         NULL,
  created_at          DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_recovery_bundle (contract_record_id, bundle_id)
);
