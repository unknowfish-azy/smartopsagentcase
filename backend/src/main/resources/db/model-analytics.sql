CREATE TABLE IF NOT EXISTS model_invocation_usage (
    id VARCHAR(36) PRIMARY KEY,
    user_id BIGINT NOT NULL,
    connection_id BIGINT NOT NULL,
    model_name VARCHAR(200) NOT NULL,
    started_at DATETIME NOT NULL,
    status VARCHAR(16) NOT NULL,
    duration_ms BIGINT,
    input_tokens BIGINT,
    output_tokens BIGINT,
    total_tokens BIGINT,
    INDEX idx_model_usage_user_time (user_id, started_at)
);
CREATE TABLE IF NOT EXISTS model_token_budget (
    user_id BIGINT NOT NULL,
    budget_month VARCHAR(7) NOT NULL,
    token_limit BIGINT,
    PRIMARY KEY (user_id, budget_month)
);
