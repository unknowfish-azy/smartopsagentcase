CREATE TABLE IF NOT EXISTS account_security (
    user_id BIGINT PRIMARY KEY,
    auth_version BIGINT NOT NULL DEFAULT 0,
    must_change_password BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS security_audit_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_id BIGINT,
    actor_username VARCHAR(64) NOT NULL,
    action VARCHAR(40) NOT NULL,
    target_id VARCHAR(64),
    outcome VARCHAR(16) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_security_audit_created (created_at, id)
);
