-- Run history required by observability queries and operation tools.
-- This migration only creates missing tables; it does not alter existing data.
CREATE TABLE IF NOT EXISTS operation_run_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    session_id BIGINT NULL,
    runtime_id VARCHAR(128) NOT NULL,
    tool_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_operation_run_trace (trace_id),
    INDEX idx_operation_run_user_time (user_id, started_at),
    INDEX idx_operation_run_tool_status (tool_id, status)
);

CREATE TABLE IF NOT EXISTS operation_run_output (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    sequence_no INT NOT NULL,
    command_text TEXT NOT NULL,
    exit_code INT NOT NULL,
    stdout_text LONGTEXT,
    stderr_text LONGTEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NOT NULL,
    CONSTRAINT fk_operation_run_output_record FOREIGN KEY (run_id)
        REFERENCES operation_run_record(id) ON DELETE CASCADE,
    UNIQUE KEY uq_operation_run_output_sequence (run_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS operation_run_evidence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    source_ref VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_operation_run_evidence_record FOREIGN KEY (run_id)
        REFERENCES operation_run_record(id) ON DELETE CASCADE,
    INDEX idx_operation_run_evidence_type (evidence_type)
);
