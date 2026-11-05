-- Flyway 接入存量库时基线为 V20261103，V20261005 会被当作"已应用"跳过；
-- 而该脚本此前从未被执行过（只靠 Config 手工注册的模块里没有它），
-- 因此存量库里可能没有这两张治理表。
-- 这里用幂等语句补齐：新库上 V20261005 已建表并建档，本脚本为空操作。
CREATE TABLE IF NOT EXISTS platform_admin_profile (
    user_id BIGINT PRIMARY KEY,
    level VARCHAR(16) NOT NULL DEFAULT 'specialist',
    appointed_by BIGINT NULL,
    appointed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT ck_platform_admin_level CHECK (level IN ('root','deputy','specialist'))
);

CREATE TABLE IF NOT EXISTS platform_admin_capability (
    user_id BIGINT NOT NULL,
    capability VARCHAR(64) NOT NULL,
    granted_by BIGINT NULL,
    granted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, capability)
);

INSERT INTO platform_admin_profile(user_id, level)
SELECT u.id, 'root' FROM app_user u
WHERE u.role='admin'
  AND NOT EXISTS (SELECT 1 FROM platform_admin_profile p WHERE p.user_id=u.id)
  AND u.id=(SELECT MIN(id) FROM app_user WHERE role='admin');

INSERT INTO platform_admin_profile(user_id, level)
SELECT u.id, 'deputy' FROM app_user u
WHERE u.role='admin'
  AND NOT EXISTS (SELECT 1 FROM platform_admin_profile p WHERE p.user_id=u.id);

INSERT INTO platform_admin_capability(user_id, capability)
SELECT p.user_id, c.capability FROM platform_admin_profile p
JOIN (SELECT 'admin.users' capability UNION ALL SELECT 'admin.config' UNION ALL SELECT 'admin.audit' UNION ALL SELECT 'admin.security' UNION ALL SELECT 'teams.view' UNION ALL SELECT 'teams.manage' UNION ALL SELECT 'teams.freeze' UNION ALL SELECT 'teams.audit' UNION ALL SELECT 'teams.approve') c
WHERE p.level IN ('root','deputy')
  AND (p.level='root' OR c.capability IN ('admin.users','admin.config','admin.audit','teams.view','teams.manage','teams.freeze','teams.audit','teams.approve'))
  AND NOT EXISTS (SELECT 1 FROM platform_admin_capability x WHERE x.user_id=p.user_id AND x.capability=c.capability);
