CREATE TABLE IF NOT EXISTS operator_memory (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    incident_key VARCHAR(255) NOT NULL,
    memory_type VARCHAR(32) NOT NULL,
    preferred_action TEXT NOT NULL,
    source_refs TEXT,
    evidence_count INT NOT NULL DEFAULT 1,
    confidence DOUBLE NOT NULL DEFAULT 0.5,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_operator_memory_user_status (user_id, status, updated_at)
);
