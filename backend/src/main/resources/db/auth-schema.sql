CREATE TABLE IF NOT EXISTS app_user (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(100) NOT NULL,
    role VARCHAR(16) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

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

CREATE TABLE IF NOT EXISTS registration_policy (
    id INT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO registration_policy(id,enabled) SELECT 1,TRUE WHERE NOT EXISTS (SELECT 1 FROM registration_policy WHERE id=1);

CREATE TABLE IF NOT EXISTS assistant_preference (
    user_id BIGINT PRIMARY KEY,
    provider_key VARCHAR(64) NOT NULL DEFAULT 'mini',
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
