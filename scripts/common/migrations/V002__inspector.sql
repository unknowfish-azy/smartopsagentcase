-- SmartOpsAgent Inspector persistence migration.
-- Additive only: existing tables are not changed or removed.

CREATE TABLE IF NOT EXISTS inspector_event (
    id VARCHAR(32) NOT NULL,
    task_id VARCHAR(128) NOT NULL,
    target VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    category VARCHAR(64),
    agent_claim TEXT,
    reason TEXT NOT NULL,
    recommendation TEXT,
    requires_human TINYINT(1) NOT NULL DEFAULT 0,
    metadata_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_inspector_event_task (task_id),
    KEY idx_inspector_event_status (status),
    KEY idx_inspector_event_severity (severity),
    KEY idx_inspector_event_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inspector_issue (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id VARCHAR(32) NOT NULL,
    category VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    reason TEXT NOT NULL,
    recommendation TEXT,
    PRIMARY KEY (id),
    KEY idx_inspector_issue_event (event_id),
    KEY idx_inspector_issue_category (category),
    CONSTRAINT fk_inspector_issue_event FOREIGN KEY (event_id)
        REFERENCES inspector_event(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inspection_evidence (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    source VARCHAR(500),
    version VARCHAR(100),
    score DOUBLE,
    PRIMARY KEY (id),
    KEY idx_inspection_evidence_event (event_id),
    CONSTRAINT fk_inspection_evidence_event FOREIGN KEY (event_id)
        REFERENCES inspector_event(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS inspection_verification (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id VARCHAR(32) NOT NULL,
    resolved TINYINT(1),
    status VARCHAR(100),
    details_json JSON,
    verified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_inspection_verification_event (event_id),
    CONSTRAINT fk_inspection_verification_event FOREIGN KEY (event_id)
        REFERENCES inspector_event(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
