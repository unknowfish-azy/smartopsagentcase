-- ============================================================
-- OPS-03 补完：资产变更历史 + 人工确认
-- ============================================================
-- 设计约束：
--   1. 变更历史只追加、不修改：任何状态/归属/关系变化都从采集、人工操作两处汇聚到这里。
--   2. actor 为空表示系统（云同步）触发，非空表示人工操作，便于区分"机器改了什么"和"人改了什么"。
--   3. 人工确认不改写 resource_uid 与采集时间，只补 confirmed_at/confirmed_by/confirmation_note，
--      让"发现"和"确认"两个事实可分别追溯。

CREATE TABLE IF NOT EXISTS asset_change_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    resource_uid VARCHAR(200) NOT NULL,
    change_type VARCHAR(32) NOT NULL,
    field_name VARCHAR(48),
    old_value VARCHAR(500),
    new_value VARCHAR(500),
    actor VARCHAR(160),
    note VARCHAR(500),
    changed_at DATETIME NOT NULL
);

CREATE INDEX ix_asset_change_uid ON asset_change_event (resource_uid, changed_at);
CREATE INDEX ix_asset_change_type ON asset_change_event (change_type, changed_at);

ALTER TABLE asset_resource ADD COLUMN confirmed_at DATETIME NULL;
ALTER TABLE asset_resource ADD COLUMN confirmed_by VARCHAR(160) NULL;
ALTER TABLE asset_resource ADD COLUMN confirmation_note VARCHAR(500) NULL;
