-- ============================================================
-- 扩展既有表：app_user 关联部门/岗位/资料字段；审计表补充 IP 与详情
-- ============================================================
-- 由 Java 侧先探测列是否存在再执行，幂等。

ALTER TABLE app_user ADD COLUMN dept_id BIGINT NULL;
ALTER TABLE app_user ADD COLUMN post_id BIGINT NULL;
ALTER TABLE app_user ADD COLUMN real_name VARCHAR(64) NULL;
ALTER TABLE app_user ADD COLUMN phone VARCHAR(32) NULL;
ALTER TABLE app_user ADD COLUMN email VARCHAR(128) NULL;

ALTER TABLE security_audit_event ADD COLUMN ip VARCHAR(64) NULL;
ALTER TABLE security_audit_event ADD COLUMN detail VARCHAR(500) NULL;
