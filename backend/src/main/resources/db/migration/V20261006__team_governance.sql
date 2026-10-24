CREATE TABLE IF NOT EXISTS team_member_capability (
    team_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    capability VARCHAR(32) NOT NULL,
    granted_by BIGINT NULL,
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, user_id, capability)
);

INSERT INTO team_member_capability(team_id, user_id, capability)
SELECT m.team_id, m.user_id, c.capability
FROM team_member m
JOIN (SELECT 'view' capability UNION ALL SELECT 'run') c
WHERE m.role IN ('owner','admin','member')
  AND NOT EXISTS (SELECT 1 FROM team_member_capability x WHERE x.team_id=m.team_id AND x.user_id=m.user_id AND x.capability=c.capability);

INSERT INTO team_member_capability(team_id, user_id, capability)
SELECT m.team_id, m.user_id, 'view'
FROM team_member m
WHERE m.role='viewer'
  AND NOT EXISTS (SELECT 1 FROM team_member_capability x WHERE x.team_id=m.team_id AND x.user_id=m.user_id AND x.capability='view');
