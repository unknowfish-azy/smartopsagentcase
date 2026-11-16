ALTER TABLE knowledge_crawl_source ADD COLUMN monitor_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE knowledge_crawl_source ADD COLUMN monitor_interval_minutes INT NOT NULL DEFAULT 60;
ALTER TABLE knowledge_crawl_source ADD COLUMN next_run_at TIMESTAMP NULL;

CREATE INDEX idx_knowledge_crawl_source_monitor_due ON knowledge_crawl_source (monitor_enabled, next_run_at);

CREATE TABLE IF NOT EXISTS web_research_task (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    task_type VARCHAR(24) NOT NULL,
    query_text VARCHAR(255),
    status VARCHAR(24) NOT NULL,
    result_count INT NOT NULL DEFAULT 0,
    error_code VARCHAR(500),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP NULL,
    INDEX idx_web_research_task_user_created (user_id, created_at)
);
