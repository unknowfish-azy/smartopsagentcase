-- ============================================================
-- 协作优化 2：草稿并发编辑的乐观锁
-- ============================================================
-- 现状：多人同时编辑同一 Agent 草稿时，后者静默覆盖前者。
-- 增加 revision（每次保存 +1）与 updated_at，供保存前比对。
-- 由 Java 侧先探测列是否存在再执行（H2/MySQL 无通用 ADD COLUMN IF NOT EXISTS）。

ALTER TABLE team_agent_version ADD COLUMN revision INT NOT NULL DEFAULT 0;
ALTER TABLE team_agent_version ADD COLUMN updated_at TIMESTAMP NULL;
