-- Agent 执行器 terminal event 落库表（P0-2 修复）。
-- 让执行轨迹可事后查询、可做 SFT 数据回流、可与 agent_decision_loop 关联。
-- 只存关联 ID 与状态，不存 payload/credentials/prompt/output。

CREATE TABLE IF NOT EXISTS agent_execution_event (
    id BIGINT NOT NULL AUTO_INCREMENT,
    event_id VARCHAR(64) NOT NULL,
    request_id VARCHAR(64) NOT NULL,
    task_id VARCHAR(64) NOT NULL,
    run_id VARCHAR(64) NOT NULL,
    step_id VARCHAR(64),
    source VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    tool_name VARCHAR(128),
    error_category VARCHAR(64),
    failure_class VARCHAR(32),
    duration_ms INT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_event_id (event_id),
    KEY idx_request_run (request_id, run_id),
    KEY idx_status (status),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
