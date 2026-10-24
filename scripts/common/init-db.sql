CREATE DATABASE IF NOT EXISTS smartops
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smartops;


-- ============================================================
-- Server
-- ============================================================

CREATE TABLE IF NOT EXISTS server (
    id BIGINT NOT NULL AUTO_INCREMENT,

    name VARCHAR(100) NOT NULL,

    host VARCHAR(255) NOT NULL,

    port INT NOT NULL DEFAULT 22,

    os VARCHAR(100),

    status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',

    description VARCHAR(500),

    created_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_server_name (name),

    KEY idx_server_status (status),

    KEY idx_server_host (host)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- Server Metric
-- ============================================================

CREATE TABLE IF NOT EXISTS server_metric (
    id BIGINT NOT NULL AUTO_INCREMENT,

    server_id BIGINT NOT NULL,

    cpu_usage DOUBLE,

    memory_usage DOUBLE,

    disk_usage DOUBLE,

    network_in DOUBLE,

    network_out DOUBLE,

    load_average DOUBLE,

    status VARCHAR(20) NOT NULL DEFAULT 'NORMAL',

    collected_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_metric_server_id (server_id),

    KEY idx_metric_collected_at (collected_at),

    KEY idx_metric_server_time (
        server_id,
        collected_at
    ),

    CONSTRAINT fk_metric_server
        FOREIGN KEY (server_id)
        REFERENCES server(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);


-- ============================================================
-- Model Connection
-- 大模型接入配置（API Key 以 AES-GCM 密文存储）
-- ============================================================

CREATE TABLE IF NOT EXISTS model_connections (
    id BIGINT NOT NULL AUTO_INCREMENT,

    user_id BIGINT NOT NULL DEFAULT 1,

    name VARCHAR(100) NOT NULL,

    provider VARCHAR(50) NOT NULL,

    base_url VARCHAR(500) NOT NULL,

    model_name VARCHAR(200) NOT NULL,

    api_key_ciphertext TEXT NOT NULL,

    api_key_last4 VARCHAR(8),

    enabled TINYINT(1) NOT NULL DEFAULT 1,

    timeout_seconds INT NOT NULL DEFAULT 60,

    created_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_model_conn_user (user_id),

    KEY idx_model_conn_enabled (enabled),

    KEY idx_model_conn_provider (provider)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- Development Data
-- ============================================================

INSERT INTO server (
    name,
    host,
    port,
    os,
    status,
    description
)
SELECT
    'demo-server-001',
    '127.0.0.1',
    22,
    'Ubuntu 22.04',
    'UNKNOWN',
    'SmartOpsAgent 开发测试服务器'
WHERE NOT EXISTS (
    SELECT 1
    FROM server
    WHERE name = 'demo-server-001'
);


-- ============================================================
-- Verification
-- ============================================================

SELECT
    COUNT(*) AS server_count
FROM server;

SELECT
    COUNT(*) AS metric_count
FROM server_metric;