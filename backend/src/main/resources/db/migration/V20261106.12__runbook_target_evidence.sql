-- OPS-11：逐目标把"已派发（SENT）/ 执行阶段结束 / 后置验证通过"分开记录。
-- 现有 status 只表达最终结果，无法复核"命令是否真的发出"与"验证是否通过"。
-- 全部为空表示该阶段未发生或未知，不得由上层补写成成功。
ALTER TABLE runbook_run_target ADD COLUMN dispatch_status VARCHAR(16) NULL;
ALTER TABLE runbook_run_target ADD COLUMN dispatched_at DATETIME NULL;
ALTER TABLE runbook_run_target ADD COLUMN executed_at DATETIME NULL;
ALTER TABLE runbook_run_target ADD COLUMN verified_at DATETIME NULL;
