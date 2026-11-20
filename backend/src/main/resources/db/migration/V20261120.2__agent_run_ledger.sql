-- Trust Ledger：Agent 运行账本（W6）。
-- 每次 Agent 运行落一行：输入、风险、工具调用、审批、结果、审计事件引用。
-- 只存结构化事实，不存凭据；JSON 列为空时写入 NULL（MySQL JSON 列不接受空串）。
CREATE TABLE IF NOT EXISTS agent_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    run_id VARCHAR(128) NOT NULL,
    request_id VARCHAR(128) NOT NULL DEFAULT '',
    user_id BIGINT NULL,
    goal TEXT NULL,
    intent VARCHAR(64) NULL,
    risk VARCHAR(16) NOT NULL DEFAULT 'LOW',
    status VARCHAR(32) NOT NULL,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'not_required',
    brief_json JSON NULL,
    tool_calls JSON NULL,
    approvals JSON NULL,
    result_json JSON NULL,
    audit_event_ids JSON NULL,
    page_context JSON NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_agent_run_run_id (run_id),
    KEY idx_agent_run_user (user_id, id),
    KEY idx_agent_run_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
