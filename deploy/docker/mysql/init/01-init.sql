-- ============================================================
-- SmartOpsAgent MySQL Initialization
-- ============================================================
-- 用途：
--   1. 初始化 SmartOpsAgent 数据库
--   2. 创建服务器基础信息表
--   3. 创建服务器监控指标表
--
-- 注意：
--   本文件仅用于开发/测试环境初始化。
--   生产环境建议使用数据库迁移工具管理表结构。
-- ============================================================


-- ============================================================
-- Database
-- ============================================================

CREATE DATABASE IF NOT EXISTS smartops
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smartops;


-- ============================================================
-- Server
-- ============================================================

CREATE TABLE IF NOT EXISTS server (
                                      id BIGINT NOT NULL AUTO_INCREMENT COMMENT '服务器ID',

                                      name VARCHAR(100) NOT NULL COMMENT '服务器名称',

    host VARCHAR(255) NOT NULL COMMENT '服务器地址',

    port INT NOT NULL DEFAULT 22 COMMENT 'SSH端口',

    os VARCHAR(100) DEFAULT NULL COMMENT '操作系统',

    status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN'
    COMMENT '服务器状态：ONLINE/OFFLINE/WARNING/UNKNOWN',

    description VARCHAR(500) DEFAULT NULL COMMENT '服务器描述',

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    COMMENT '创建时间',

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ON UPDATE CURRENT_TIMESTAMP
    COMMENT '更新时间',

    PRIMARY KEY (id),

    UNIQUE KEY uk_server_name (name),

    KEY idx_server_status (status),

    KEY idx_server_host (host)

    ) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='服务器基础信息';


-- ============================================================
-- Server Metric
-- ============================================================

CREATE TABLE IF NOT EXISTS server_metric (
                                             id BIGINT NOT NULL AUTO_INCREMENT COMMENT '监控指标ID',

                                             server_id BIGINT NOT NULL COMMENT '服务器ID',

                                             cpu_usage DOUBLE DEFAULT NULL COMMENT 'CPU使用率，0~100',

                                             memory_usage DOUBLE DEFAULT NULL COMMENT '内存使用率，0~100',

                                             disk_usage DOUBLE DEFAULT NULL COMMENT '磁盘使用率，0~100',

                                             network_in DOUBLE DEFAULT NULL COMMENT '网络入流量',

                                             network_out DOUBLE DEFAULT NULL COMMENT '网络出流量',

                                             load_average DOUBLE DEFAULT NULL COMMENT '系统平均负载',

                                             status VARCHAR(20) NOT NULL DEFAULT 'NORMAL'
    COMMENT '指标状态：NORMAL/WARNING/CRITICAL',

    collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    COMMENT '采集时间',

    PRIMARY KEY (id),

    KEY idx_metric_server_id (server_id),

    KEY idx_metric_collected_at (collected_at),

    KEY idx_metric_server_time (
                                   server_id,
                                   collected_at
                               ),

    CONSTRAINT fk_metric_server
    FOREIGN KEY (server_id)
    REFERENCES server (id)
    ON DELETE CASCADE
    ON UPDATE CASCADE

    ) ENGINE=InnoDB
    DEFAULT CHARSET=utf8mb4
    COLLATE=utf8mb4_unicode_ci
    COMMENT='服务器监控指标';


-- ============================================================
-- Development Seed Data
-- ============================================================
-- 仅用于开发环境验证。
-- 不包含真实服务器地址、密码或凭据。
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
-- Demo Metrics
-- ============================================================

INSERT INTO server_metric (
    server_id,
    cpu_usage,
    memory_usage,
    disk_usage,
    network_in,
    network_out,
    load_average,
    status,
    collected_at
)
SELECT
    id,
    25.50,
    48.20,
    61.30,
    1024.00,
    2048.00,
    0.85,
    'NORMAL',
    CURRENT_TIMESTAMP
FROM server
WHERE name = 'demo-server-001'
  AND NOT EXISTS (
    SELECT 1
    FROM server_metric
    WHERE server_id = server.id
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