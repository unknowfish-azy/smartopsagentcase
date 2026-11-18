-- 控制面增强：按比例灰度 + 多级审批
-- rollout_percent：生效版本承接的流量百分比，100 表示全量
-- requested_percent：提交审批时申请的灰度比例，审批通过后据此发布
ALTER TABLE model_gateway_config_version ADD COLUMN rollout_percent INT NOT NULL DEFAULT 100;
ALTER TABLE model_gateway_config_version ADD COLUMN requested_percent INT NULL;
ALTER TABLE model_gateway_config_version ADD COLUMN submitted_by BIGINT NULL;
ALTER TABLE model_gateway_config_version ADD COLUMN submitted_at TIMESTAMP NULL;
ALTER TABLE model_gateway_config_version ADD COLUMN approved_at TIMESTAMP NULL;
ALTER TABLE model_gateway_config_version ADD COLUMN rejection_comment VARCHAR(500) NULL;

CREATE TABLE IF NOT EXISTS model_gateway_config_approval (
    id BIGINT PRIMARY KEY,
    version_id BIGINT NOT NULL,
    approver_id BIGINT NOT NULL,
    action VARCHAR(16) NOT NULL,
    comment VARCHAR(500) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_gateway_config_approval (version_id, approver_id),
    INDEX idx_gateway_approval_version (version_id)
);
