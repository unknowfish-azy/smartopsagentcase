-- ============================================================
-- SmartOpsAgent Model Connections
-- ============================================================

CREATE TABLE IF NOT EXISTS model_connections (
                                                 id BIGINT PRIMARY KEY AUTO_INCREMENT,

                                                 user_id BIGINT NULL COMMENT '所属用户 ID',

                                                 name VARCHAR(100) NOT NULL COMMENT '连接名称',

    provider VARCHAR(50) NOT NULL COMMENT 'Provider 类型',

    base_url VARCHAR(500) NOT NULL COMMENT '模型 API Base URL',

    model_name VARCHAR(200) NOT NULL COMMENT '模型名称',

    api_key_ciphertext TEXT NOT NULL COMMENT 'AES-GCM 加密后的 API Key',

    api_key_last4 VARCHAR(4) NULL COMMENT 'API Key 最后四位，用于展示',

    enabled TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',

    timeout_seconds INT NOT NULL DEFAULT 60 COMMENT '请求超时秒数',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_model_connections_user_id (user_id),

    INDEX idx_model_connections_provider (provider),

    INDEX idx_model_connections_enabled (enabled)
    ) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci;