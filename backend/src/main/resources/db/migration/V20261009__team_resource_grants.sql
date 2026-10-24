CREATE TABLE IF NOT EXISTS team_resource_grant (
    team_id BIGINT NOT NULL,
    resource_type VARCHAR(32) NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    user_id BIGINT NOT NULL,
    capability VARCHAR(32) NOT NULL,
    granted_by BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, resource_type, resource_id, user_id, capability),
    INDEX ix_team_resource_grant_user (team_id, user_id, resource_type)
);
