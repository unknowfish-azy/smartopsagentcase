-- P0-3 处置动作风险评估门：审计日志表
-- 记录每次风险评估的输入、命中规则、风险等级与处置结果，支持事后追溯。
CREATE TABLE IF NOT EXISTS risk_assessment_log (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    tool_id VARCHAR(128),
    command_text TEXT,
    risk_level VARCHAR(16) NOT NULL,
    risk_score INT NOT NULL,
    hit_rules TEXT,
    allowed BOOLEAN NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_risk_assessment_user_time (user_id, created_at),
    INDEX idx_risk_assessment_level (risk_level, created_at)
);
