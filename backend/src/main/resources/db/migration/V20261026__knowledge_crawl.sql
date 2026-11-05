CREATE TABLE IF NOT EXISTS knowledge_crawl_source (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    library_id BIGINT NOT NULL,
    name VARCHAR(120) NOT NULL,
    seed_url VARCHAR(512) NOT NULL,
    max_pages INT NOT NULL DEFAULT 20,
    depth INT NOT NULL DEFAULT 1,
    last_run_at TIMESTAMP NULL,
    last_status VARCHAR(32),
    last_error VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_knowledge_crawl_source_user_library (user_id, library_id)
);

CREATE TABLE IF NOT EXISTS knowledge_crawl_page (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    url VARCHAR(512) NOT NULL,
    title VARCHAR(255),
    content_md MEDIUMTEXT,
    content_hash CHAR(64),
    entry_id BIGINT,
    change_type VARCHAR(16) NOT NULL,
    fetched_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_knowledge_crawl_page_source (source_id),
    INDEX idx_knowledge_crawl_page_user (user_id)
);
