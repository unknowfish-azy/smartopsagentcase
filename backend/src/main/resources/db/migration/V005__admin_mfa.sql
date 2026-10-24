CREATE TABLE IF NOT EXISTS account_mfa (
    user_id BIGINT PRIMARY KEY,
    secret_encrypted VARCHAR(512),
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    last_used_step BIGINT NOT NULL DEFAULT -1,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS account_mfa_recovery (
    user_id BIGINT NOT NULL,
    code_hash VARCHAR(64) NOT NULL,
    PRIMARY KEY (user_id, code_hash)
);

CREATE TABLE IF NOT EXISTS account_security_notice (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    kind VARCHAR(40) NOT NULL,
    message VARCHAR(240) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at TIMESTAMP NULL,
    INDEX ix_account_notice_user (user_id, id)
);
