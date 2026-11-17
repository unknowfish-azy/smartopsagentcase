-- 自愈闭环调参：PID 控制器状态表
-- 借鉴机器人 PID 闭环控制思想：
--   P  = Kp × e            当前误差项
--   I  = Ki × Σe(衰减)     历史积累项（带指数衰减，防止饱和）
--   M  = 矩阵选最优组合    多脚本并行时的策略矩阵
-- 核心回路：
--   告警 → PID 读状态 → 算处置强度（P+I）→ 传递给处置脚本参数
--   执行后 → 读 resolved_at 后的指标回差 → 更新积分项 Σe
-- 降级：
--   无 PID 记录 → 默认强度 0.5（保守）
--   无回差数据 → 跳过 I 项积累
--   脚本执行失败 → I 项不积累，下次 P 按新误差算

CREATE TABLE sentinel_pid_state (
    id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    metric VARCHAR(64) NOT NULL,
    kp DOUBLE NOT NULL DEFAULT 0.6,          -- 比例增益：当前误差权重
    ki DOUBLE NOT NULL DEFAULT 0.1,          -- 积分增益：历史误差积累权重
    kd DOUBLE NOT NULL DEFAULT 0.0,          -- 微分增益：误差变化率（暂不用，保留位）
    integral DOUBLE NOT NULL DEFAULT 0.0,    -- 积分项 Σe（带衰减）
    last_error DOUBLE NOT NULL DEFAULT 0.0,  -- 上次误差（e = observed - threshold）
    last_intensity DOUBLE NOT NULL DEFAULT 0.5, -- 上次执行的处置强度（0~1）
    last_executed_at TIMESTAMP NULL,          -- 上次执行处置的时间
    last_error_after DOUBLE NULL,             -- 上次处置后指标回差（用于判断收敛）
    execution_count INT NOT NULL DEFAULT 0,   -- 累计执行次数（用于动态调参参考）
    enabled TINYINT(1) NOT NULL DEFAULT 1,   -- 是否启用 PID 调节
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_task_metric (task_id, metric),
    KEY idx_pid_task (task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- sentinel_script_run 加 PID 反馈字段：记录每次处置用的强度和执行后指标回差
ALTER TABLE sentinel_script_run ADD COLUMN pid_intensity DOUBLE NULL AFTER variables_json;
ALTER TABLE sentinel_script_run ADD COLUMN pid_error_after DOUBLE NULL AFTER pid_intensity;
