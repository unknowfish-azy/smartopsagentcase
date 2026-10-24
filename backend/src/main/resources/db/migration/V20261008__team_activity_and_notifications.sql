CREATE TABLE IF NOT EXISTS team_activity_event (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    team_id BIGINT NOT NULL,
    actor_id BIGINT NULL,
    action VARCHAR(64) NOT NULL,
    target_id VARCHAR(128) NULL,
    details_json TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_team_activity_team_created (team_id, created_at, id)
);
