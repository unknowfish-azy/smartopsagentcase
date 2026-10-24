CREATE TABLE IF NOT EXISTS chat_conversation (
    id VARCHAR(36) PRIMARY KEY,
    owner_id BIGINT NOT NULL,
    team_id BIGINT,
    scope_key VARCHAR(64) NOT NULL,
    title VARCHAR(80) NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_message (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL,
    request_id VARCHAR(36) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    actor_id BIGINT NOT NULL,
    role VARCHAR(16) NOT NULL,
    content TEXT NOT NULL,
    created_at BIGINT NOT NULL,
    UNIQUE (conversation_id, request_id, role),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chat_attachment (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL,
    request_id VARCHAR(36) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    name VARCHAR(160) NOT NULL,
    media_type VARCHAR(64) NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'FILE',
    byte_size BIGINT NOT NULL,
    content LONGBLOB NOT NULL,
    message_id VARCHAR(36),
    created_at BIGINT NOT NULL,
    UNIQUE (conversation_id, request_id),
    FOREIGN KEY (conversation_id) REFERENCES chat_conversation(id) ON DELETE CASCADE,
    FOREIGN KEY (message_id) REFERENCES chat_message(id) ON DELETE CASCADE
);
