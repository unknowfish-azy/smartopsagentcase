-- OPS-09 静默治理：审批状态与外部静默同步结果。
--
-- 口径：
--   1. status 只有 ACTIVE 才真正抑制告警；PENDING_APPROVAL 表示"已申请、未生效"；
--   2. external_status 是外部平台（Alertmanager）的真实同步结果，
--      NOT_CONFIGURED / FAILED 都不能被当成"已静默成功"；
--   3. 撤销时先撤销外部静默，外部失败则本地不删，避免"看起来撤销了、实际还在静默"。

ALTER TABLE sentinel_silence ADD COLUMN status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE sentinel_silence ADD COLUMN approved_by BIGINT NULL;
ALTER TABLE sentinel_silence ADD COLUMN approved_at DATETIME NULL;
ALTER TABLE sentinel_silence ADD COLUMN external_id VARCHAR(128) NULL;
ALTER TABLE sentinel_silence ADD COLUMN external_status VARCHAR(32) NOT NULL DEFAULT 'NOT_CONFIGURED';
ALTER TABLE sentinel_silence ADD COLUMN external_error VARCHAR(500) NULL;

CREATE INDEX ix_silence_status ON sentinel_silence (status, ends_at);
