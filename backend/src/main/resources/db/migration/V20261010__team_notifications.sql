CREATE TABLE IF NOT EXISTS team_notification (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    team_id BIGINT NULL,
    user_id BIGINT NOT NULL,
    notification_type VARCHAR(48) NOT NULL,
    reference_id VARCHAR(128) NULL,
    message VARCHAR(500) NOT NULL,
    read_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_team_notification_user (user_id, read_at, id),
    INDEX ix_team_notification_team (team_id, id)
);
