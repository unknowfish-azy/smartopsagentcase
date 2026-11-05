-- ============================================================
-- OPS-07：数据库真实诊断审计
-- ============================================================
-- 设计约束：
--   1. 每条诊断（成功与失败）都写一行，便于区分"诊断过但没采到"和"根本没诊断"。
--   2. 只存引擎、目标、状态与稳定错误码；不存凭据、不存未脱敏 SQL。
--   3. check_summary 是各检查项状态摘要（NAME=STATUS），不是 SQL 原文。

CREATE TABLE IF NOT EXISTS database_diagnosis_audit (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_id BIGINT NULL,
    team_id BIGINT NULL,
    engine VARCHAR(32) NOT NULL,
    target_host VARCHAR(255) NOT NULL,
    target_port INT NOT NULL,
    database_name VARCHAR(128) NOT NULL,
    credential_source VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    check_summary VARCHAR(1000),
    error_code VARCHAR(64),
    created_at DATETIME NOT NULL
);
CREATE INDEX ix_db_diag_audit_time ON database_diagnosis_audit (created_at);
