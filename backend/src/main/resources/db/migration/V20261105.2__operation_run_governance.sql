-- ============================================================
-- OPS-04：执行恢复与资源治理
-- ============================================================
-- 目标：让 Java 侧 Run 成为可恢复的权威状态，而不是"进程内跑完再写一行状态"。
--
--   idempotency_key   同一用户同一键只允许一次执行（防重复副作用）
--   attempt           预留的执行代次；当前实现固定为 1，不自动重试
--   deadline_at       整单绝对截止时间（不是单条命令超时）
--   lease_expires_at  租约；无心跳即视为悬挂
--   heartbeat_at      最近一次心跳
--   cancel_requested  取消标记，在命令之间轮询生效
--   output_bytes      已落库输出预算用量
--
-- 为什么加 verification 语义：远端动作后中断时"退出码未知"不等于失败，
-- 也不等于成功；把它归为 UNCERTAIN 并写入证据，避免被当成可安全重试的失败。

ALTER TABLE operation_run_record ADD COLUMN idempotency_key VARCHAR(128) NULL;
ALTER TABLE operation_run_record ADD COLUMN attempt INT NOT NULL DEFAULT 1;
ALTER TABLE operation_run_record ADD COLUMN deadline_at DATETIME NULL;
ALTER TABLE operation_run_record ADD COLUMN lease_expires_at DATETIME NULL;
ALTER TABLE operation_run_record ADD COLUMN heartbeat_at DATETIME NULL;
ALTER TABLE operation_run_record ADD COLUMN cancel_requested TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE operation_run_record ADD COLUMN output_bytes BIGINT NOT NULL DEFAULT 0;

CREATE UNIQUE INDEX uq_operation_run_idempotency ON operation_run_record (user_id, idempotency_key);

CREATE INDEX idx_operation_run_recovery ON operation_run_record (status, lease_expires_at);

ALTER TABLE operation_run_output ADD COLUMN truncated TINYINT(1) NOT NULL DEFAULT 0;
ALTER TABLE operation_run_output ADD COLUMN output_bytes BIGINT NOT NULL DEFAULT 0;
