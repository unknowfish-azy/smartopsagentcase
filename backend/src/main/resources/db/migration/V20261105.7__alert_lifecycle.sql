-- ============================================================
-- P0-03 告警生命周期：分组 / 自动恢复 / 静默窗口 / 死信
-- ============================================================
-- 已有能力（不改动）：告警表、处置时间线、通知投递记录、确认/关闭/派单。
-- 本次只补"缺口"：
--   1. group_key —— 同一故障的多次告警归到一组，便于"一件事一次看"；
--   2. recovered_at —— 指标恢复自动进入待关闭，与人工处置区分开；
--   3. sentinel_silence —— 静默/维护窗口，窗口内不新建告警、不通知；
--   4. dead_lettered —— 投递失败且重试耗尽后进入死信，保留记录不静默丢弃。

ALTER TABLE sentinel_alert ADD COLUMN group_key VARCHAR(160) NULL;
ALTER TABLE sentinel_alert ADD COLUMN recovered_at DATETIME NULL;

ALTER TABLE sentinel_notification ADD COLUMN dead_lettered BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS sentinel_silence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    scope_type VARCHAR(16) NOT NULL,
    scope_id BIGINT NULL,
    reason VARCHAR(200) NOT NULL,
    starts_at DATETIME NOT NULL,
    ends_at DATETIME NOT NULL,
    created_by BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_silence_scope ON sentinel_silence (scope_type, scope_id, ends_at);
CREATE INDEX ix_alert_group ON sentinel_alert (group_key, fired_at);
