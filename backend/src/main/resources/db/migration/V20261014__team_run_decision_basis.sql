-- ============================================================
-- 协作优化 1：审批附「决策依据」
-- ============================================================
-- 现状：approve 只记录了"谁批的"，没有记录"基于什么批的"。
-- 竞赛与合规场景下，"谁基于哪条告警/哪段日志/哪次预览批准的"才是可追责的凭据。
-- 幂等：H2 与 MySQL 都不支持 ADD COLUMN IF NOT EXISTS 的通用写法，
-- 因此由 Java 侧先探测列是否存在（见 TeamAgentRunConfig）。

ALTER TABLE team_agent_run ADD COLUMN decision_basis VARCHAR(800) NULL;
