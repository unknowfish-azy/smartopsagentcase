-- AgentGuard 智测盾：测评任务与逐条结果
-- 一个 run 对应一次「目标 + 套件」测评；逐条用例结果落 guard_case_result，分数可由明细复算。
CREATE TABLE IF NOT EXISTS guard_run (
    id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    target_type VARCHAR(32) NOT NULL,
    target_id VARCHAR(64) NOT NULL,
    target_name VARCHAR(128) NOT NULL,
    suite VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    score INT NULL,
    risk_level VARCHAR(16) NULL,
    total_cases INT NOT NULL DEFAULT 0,
    passed_cases INT NOT NULL DEFAULT 0,
    failed_cases INT NOT NULL DEFAULT 0,
    error_cases INT NOT NULL DEFAULT 0,
    is_baseline TINYINT(1) NOT NULL DEFAULT 0,
    baseline_run_id BIGINT NULL,
    regression_verdict VARCHAR(24) NULL,
    regression_summary VARCHAR(255) NULL,
    error_message VARCHAR(512) NULL,
    started_at TIMESTAMP NULL,
    finished_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guard_run_user (user_id, id),
    KEY idx_guard_run_target (user_id, target_type, target_id, is_baseline)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS guard_case_result (
    id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    run_id BIGINT NOT NULL,
    case_id VARCHAR(64) NOT NULL,
    category VARCHAR(32) NOT NULL,
    severity VARCHAR(16) NOT NULL,
    title VARCHAR(160) NOT NULL,
    prompt TEXT NOT NULL,
    response MEDIUMTEXT NULL,
    verdict VARCHAR(16) NOT NULL,
    risk_score INT NOT NULL DEFAULT 0,
    hit_rules VARCHAR(500) NULL,
    detector VARCHAR(40) NOT NULL,
    owasp VARCHAR(120) NULL,
    latency_ms INT NOT NULL DEFAULT 0,
    error_message VARCHAR(300) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guard_case_run (run_id, id),
    KEY idx_guard_case_verdict (run_id, verdict)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
