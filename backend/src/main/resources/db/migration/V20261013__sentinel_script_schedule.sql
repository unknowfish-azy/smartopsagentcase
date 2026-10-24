-- ============================================================
-- 脚本执行模式与调度（手动 / 定时 / 告警联动）
-- ============================================================
-- 设计要点：三种触发模式**共用同一条执行链** ——
-- 都由 SentinelScriptRunner 生成 MultiExec 预览并登记为待审批，
-- 真正的执行仍必须由人通过既有 /api/operations/multi-exec/execute 完成。
-- 本迁移不提供、也不允许任何"直接执行"的字段或开关。
-- 幂等，可由 ResourceDatabasePopulator 重复执行。

CREATE TABLE IF NOT EXISTS sentinel_script_schedule (
  id           BIGINT      NOT NULL AUTO_INCREMENT,
  script_id    BIGINT      NOT NULL,
  user_id      BIGINT      NOT NULL,
  cron_expr    VARCHAR(64) NOT NULL,
  runtime_id   VARCHAR(128) NULL,
  enabled      TINYINT(1)  NOT NULL DEFAULT 1,
  last_fire_at DATETIME    NULL,
  next_fire_at DATETIME    NULL,
  created_at   DATETIME    NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_script_schedule_due (enabled, next_fire_at),
  CONSTRAINT fk_schedule_script FOREIGN KEY (script_id) REFERENCES sentinel_script (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
