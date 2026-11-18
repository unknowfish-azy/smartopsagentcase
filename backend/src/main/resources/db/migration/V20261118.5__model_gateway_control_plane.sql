-- 模型网关控制面：配置版本、内存快照与发布审计
-- 工作区（草稿区）= model_gateway_group / model_gateway_route / model_connections，
-- 管理端照常编辑；生效区 = 本表 status='ACTIVE' 的 snapshot_json。
-- 网关请求只读内存快照，控制面变更不进入请求链路。
CREATE TABLE IF NOT EXISTS model_gateway_config_version (
    id BIGINT PRIMARY KEY,
    version_no INT NOT NULL,
    status VARCHAR(16) NOT NULL,
    summary VARCHAR(500) NOT NULL,
    snapshot_json LONGTEXT NOT NULL,
    diff_json LONGTEXT NULL,
    gate_report_json LONGTEXT NULL,
    content_hash CHAR(64) NOT NULL,
    created_by BIGINT NOT NULL,
    activated_by BIGINT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    activated_at TIMESTAMP NULL,
    UNIQUE KEY uk_gateway_config_version_no (version_no),
    INDEX idx_gateway_config_status (status, version_no)
);

-- 让每一次网关调用都能回溯到当时生效的配置版本
ALTER TABLE model_gateway_invocation ADD COLUMN config_version INT NULL AFTER model_name;
