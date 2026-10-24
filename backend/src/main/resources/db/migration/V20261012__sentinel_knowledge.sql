-- ============================================================
-- 哨兵告警 → 知识沉淀（协作优化第 3 点）
-- ============================================================
-- 一次已闭环的告警（现象 → 证据 → 研判 → 处置时间线 → 关闭说明）
-- 沉淀为「知识候选」，进入团队复核流程后采纳进知识库。
-- 幂等，可由 ResourceDatabasePopulator 重复执行。

CREATE TABLE IF NOT EXISTS sentinel_knowledge_candidate (
  id         BIGINT       NOT NULL AUTO_INCREMENT,
  alert_id   BIGINT       NOT NULL,
  user_id    BIGINT       NOT NULL,
  title      VARCHAR(200) NOT NULL,
  status     VARCHAR(24)  NOT NULL DEFAULT 'PENDING_REVIEW',
  content    MEDIUMTEXT   NOT NULL,
  reviewer_id BIGINT      NULL,
  reviewed_at DATETIME    NULL,
  created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_sentinel_kc_user (user_id, status),
  KEY idx_sentinel_kc_alert (alert_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
