-- ============================================================
-- PERF-01：哨兵采集的有界并发调度
-- ============================================================
-- 原实现：单线程 for 循环逐个采集，50 个慢目标会把一轮拉长到 750s，
-- 且到期判定只看 last_seen_at —— 失败任务没有明确的"下次采集时间"，会被反复重采。
--
--   claimed_by           认领者标识（实例 ID），配合租约实现多副本互斥
--   lease_expires_at     认领租约；超时未释放才允许其他副本接手
--   next_run_at          下一次采集时间（成功=周期，失败=指数退避+抖动）
--   consecutive_failures 连续失败次数，用于退避计算；成功后归零
--
-- 关键点：认领用条件 UPDATE（claimed_by 为空或租约过期）而不是先查后改，
-- 因此两个副本并发轮询时只有一个能认领成功，不会重复采集同一个任务。

ALTER TABLE sentinel_task ADD COLUMN claimed_by VARCHAR(96) NULL;
ALTER TABLE sentinel_task ADD COLUMN lease_expires_at TIMESTAMP NULL;
ALTER TABLE sentinel_task ADD COLUMN next_run_at TIMESTAMP NULL;
ALTER TABLE sentinel_task ADD COLUMN consecutive_failures INT NOT NULL DEFAULT 0;

CREATE INDEX idx_sentinel_task_due ON sentinel_task (enabled, next_run_at, lease_expires_at);
