-- 资源雷达 P1：来源注册、采集运行日志、资源条目、证据链、站内日报。
-- 纪律：采集结果一律以 DRAFT 入库；AI 定级（P2）只允许写 quality/score/category，
--       不得改变 status，也不得让草案条目进入 Agent 决策上下文。

CREATE TABLE IF NOT EXISTS radar_source (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    collector_type VARCHAR(24) NOT NULL,
    url VARCHAR(512) NOT NULL,
    channel VARCHAR(32) NOT NULL,
    trust_level VARCHAR(4) NOT NULL DEFAULT 'L4',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    interval_minutes INT NOT NULL DEFAULT 360,
    last_run_at TIMESTAMP NULL,
    next_run_at TIMESTAMP NULL,
    last_status VARCHAR(24) NULL,
    last_error VARCHAR(500) NULL,
    created_by BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_radar_source_url (url),
    INDEX idx_radar_source_due (enabled, next_run_at),
    INDEX idx_radar_source_channel (channel)
);

CREATE TABLE IF NOT EXISTS radar_run_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NOT NULL,
    trigger_type VARCHAR(16) NOT NULL DEFAULT 'MANUAL',
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL,
    fetched INT NOT NULL DEFAULT 0,
    kept INT NOT NULL DEFAULT 0,
    skipped INT NOT NULL DEFAULT 0,
    failed INT NOT NULL DEFAULT 0,
    error VARCHAR(500) NULL,
    INDEX idx_radar_run_log_source (source_id, started_at)
);

CREATE TABLE IF NOT EXISTS radar_item (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NOT NULL,
    channel VARCHAR(32) NOT NULL,
    external_id VARCHAR(255) NULL,
    title VARCHAR(512) NOT NULL,
    summary TEXT NULL,
    url VARCHAR(512) NOT NULL,
    url_hash CHAR(64) NOT NULL,
    kind VARCHAR(24) NOT NULL,
    category VARCHAR(48) NOT NULL,
    obtain VARCHAR(24) NOT NULL,
    quality INT NOT NULL DEFAULT 3,
    trust_level VARCHAR(4) NOT NULL DEFAULT 'L4',
    freshness DOUBLE NOT NULL DEFAULT 0,
    score DOUBLE NOT NULL DEFAULT 0,
    risk_flags VARCHAR(255) NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'DRAFT',
    published_at TIMESTAMP NULL,
    expires_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_radar_item_url_hash (url_hash),
    INDEX idx_radar_item_query (channel, status, score),
    INDEX idx_radar_item_expires (status, expires_at)
);

CREATE TABLE IF NOT EXISTS radar_item_evidence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    item_id BIGINT NOT NULL,
    evidence_url VARCHAR(512) NOT NULL,
    evidence_type VARCHAR(24) NOT NULL,
    captured_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP NULL,
    verified_by BIGINT NULL,
    note VARCHAR(500) NULL,
    INDEX idx_radar_item_evidence_item (item_id)
);

CREATE TABLE IF NOT EXISTS radar_digest (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    channel VARCHAR(32) NULL,
    period_start TIMESTAMP NOT NULL,
    period_end TIMESTAMP NOT NULL,
    content_md TEXT NOT NULL,
    item_ids TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_radar_digest_user (user_id, created_at)
);
