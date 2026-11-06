-- ============================================================
-- SEC-05：团队运行的 grant 绑定与生命周期补齐
-- ============================================================
-- 1) grant_digest：审批时服务端按「规范化参数 + toolId + 工具版本 + 审批人」计算的绑定摘要，
--    与 preview_digest（渲染命令摘要）互补：前者证明"批的就是将要执行的参数"，
--    后者继续用于发现预览与执行之间的渲染漂移。
-- 2) canceled_by / canceled_at / cancel_reason：审批可撤回（CANCELED），撤销后 grant 立即失效。
-- 3) idempotency_key：同一申请人重复提交返回既有运行，唯一索引兜住并发窗口。

ALTER TABLE team_agent_run ADD COLUMN grant_digest VARCHAR(64) NULL;
ALTER TABLE team_agent_run ADD COLUMN canceled_by BIGINT NULL;
ALTER TABLE team_agent_run ADD COLUMN canceled_at TIMESTAMP NULL;
ALTER TABLE team_agent_run ADD COLUMN cancel_reason VARCHAR(400) NULL;
ALTER TABLE team_agent_run ADD COLUMN idempotency_key VARCHAR(128) NULL;

CREATE UNIQUE INDEX ux_team_agent_run_idempotency ON team_agent_run(team_id, requester_id, idempotency_key);
