CREATE TABLE IF NOT EXISTS team_invite_link (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    team_id BIGINT NOT NULL,
    token_hash CHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    created_by BIGINT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active',
    expires_at TIMESTAMP NOT NULL,
    used_by BIGINT NULL,
    used_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_team_invite_link_token (token_hash),
    INDEX ix_team_invite_link_team (team_id, status, expires_at)
);

CREATE TABLE IF NOT EXISTS team_resource_share (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    team_id BIGINT NOT NULL,
    resource_type VARCHAR(32) NOT NULL,
    resource_id BIGINT NOT NULL,
    shared_by BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_team_resource_share (team_id, resource_type, resource_id),
    INDEX ix_team_resource_share_owner (shared_by, resource_type)
);
