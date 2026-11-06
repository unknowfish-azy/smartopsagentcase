DROP TABLE IF EXISTS server_metric;
DROP TABLE IF EXISTS server;

CREATE TABLE server (
                        id BIGINT AUTO_INCREMENT PRIMARY KEY,
                        owner_id BIGINT,
                        name VARCHAR(100) NOT NULL,
                        host VARCHAR(255) NOT NULL,
                        port INT NOT NULL,
                        os VARCHAR(50),
                        status VARCHAR(20) NOT NULL,
                        description VARCHAR(500),
                        created_at TIMESTAMP NOT NULL,
                        updated_at TIMESTAMP NOT NULL
);

CREATE TABLE server_metric (
                               id BIGINT AUTO_INCREMENT PRIMARY KEY,
                               server_id BIGINT NOT NULL,
                               cpu_usage DOUBLE NOT NULL,
                               memory_usage DOUBLE NOT NULL,
                               disk_usage DOUBLE NOT NULL,
                               network_in DOUBLE,
                               network_out DOUBLE,
                               load_average DOUBLE,
                               status VARCHAR(20) NOT NULL,
                               collected_at TIMESTAMP NOT NULL,

                               CONSTRAINT fk_metric_server
                                   FOREIGN KEY (server_id)
                                       REFERENCES server(id)
                                       ON DELETE CASCADE
);

CREATE INDEX idx_server_metric_server_time
    ON server_metric(server_id, collected_at);

CREATE TABLE IF NOT EXISTS operation_session_group (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    parent_id BIGINT,
    name VARCHAR(120) NOT NULL,
    sort_order INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operation_credential (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    type VARCHAR(32) NOT NULL,
    secret_ciphertext CLOB NOT NULL,
    last4 VARCHAR(4),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operation_session (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    group_id BIGINT,
    name VARCHAR(120) NOT NULL,
    protocol VARCHAR(32) NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    username VARCHAR(255) NOT NULL,
    credential_id BIGINT,
    identity_path VARCHAR(2048),
    jump_session_id BIGINT,
    working_directory VARCHAR(2048),
    tags_json CLOB,
    description CLOB,
    accent VARCHAR(32),
    favorite BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(32) NOT NULL DEFAULT 'IDLE',
    last_connected_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operation_known_host (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    session_id BIGINT NOT NULL,
    host VARCHAR(255) NOT NULL,
    port INT NOT NULL,
    algorithm VARCHAR(64) NOT NULL,
    fingerprint VARCHAR(255) NOT NULL,
    public_key CLOB NOT NULL,
    trusted_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (session_id, host, port)
);

CREATE TABLE IF NOT EXISTS inspector_event (
    id VARCHAR(32) PRIMARY KEY,
    task_id VARCHAR(128) NOT NULL,
    target VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    category VARCHAR(64),
    agent_claim CLOB,
    reason CLOB NOT NULL,
    recommendation CLOB,
    requires_human BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_json CLOB,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS inspector_issue (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(32) NOT NULL,
    category VARCHAR(64) NOT NULL,
    severity VARCHAR(32) NOT NULL,
    reason CLOB NOT NULL,
    recommendation CLOB,
    CONSTRAINT fk_test_inspector_issue FOREIGN KEY (event_id)
        REFERENCES inspector_event(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inspection_evidence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(32) NOT NULL,
    content CLOB NOT NULL,
    source VARCHAR(500),
    version VARCHAR(100),
    score DOUBLE,
    CONSTRAINT fk_test_inspection_evidence FOREIGN KEY (event_id)
        REFERENCES inspector_event(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inspection_verification (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    event_id VARCHAR(32) NOT NULL,
    resolved BOOLEAN,
    status VARCHAR(100),
    details_json CLOB,
    verified_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_test_inspection_verification FOREIGN KEY (event_id)
        REFERENCES inspector_event(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS operation_run_record (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    trace_id VARCHAR(64) NOT NULL UNIQUE,
    user_id BIGINT NOT NULL,
    session_id BIGINT,
    runtime_id VARCHAR(128) NOT NULL,
    tool_id VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS operation_run_output (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    sequence_no INT NOT NULL,
    command_text CLOB NOT NULL,
    exit_code INT NOT NULL,
    stdout_text CLOB,
    stderr_text CLOB,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP NOT NULL,
    UNIQUE (run_id, sequence_no)
);

CREATE TABLE IF NOT EXISTS operation_run_evidence (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    run_id BIGINT NOT NULL,
    evidence_type VARCHAR(64) NOT NULL,
    content CLOB NOT NULL,
    source_ref VARCHAR(255),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_candidate (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    source_run_id BIGINT NOT NULL,
    trace_id VARCHAR(64) NOT NULL,
    tool_id VARCHAR(128) NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary CLOB NOT NULL,
    content_markdown CLOB NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING_REVIEW',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, source_run_id),
    CONSTRAINT fk_knowledge_candidate_run FOREIGN KEY (source_run_id) REFERENCES operation_run_record(id)
);
