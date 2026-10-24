CREATE TABLE IF NOT EXISTS personal_knowledge_library (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    description VARCHAR(500),
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_personal_knowledge_library_user (user_id, status)
);

CREATE TABLE IF NOT EXISTS personal_knowledge_entry (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    library_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary VARCHAR(1000) NOT NULL,
    content_markdown LONGTEXT NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    source_ref VARCHAR(255),
    verification_status VARCHAR(32) NOT NULL DEFAULT 'UNVERIFIED',
    version INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_personal_knowledge_entry_library FOREIGN KEY (library_id) REFERENCES personal_knowledge_library(id) ON DELETE CASCADE,
    INDEX idx_personal_knowledge_entry_user_library (user_id, library_id, updated_at)
);
