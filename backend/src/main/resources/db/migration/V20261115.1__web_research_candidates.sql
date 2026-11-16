-- 联网检索正文快照 → 候选知识人工审核。
-- 运维运行候选继续引用 source_run_id；网页候选将其留空并使用 source_task_id，避免伪造运维运行记录。
-- 原 fk_knowledge_candidate_run 继续保留，NULL 不参与外键校验，既有运维候选的引用完整性不变。
ALTER TABLE knowledge_candidate MODIFY COLUMN source_run_id BIGINT NULL;
ALTER TABLE knowledge_candidate ADD COLUMN source_task_id BIGINT NULL;
ALTER TABLE knowledge_candidate ADD COLUMN source_url VARCHAR(255) NULL;
ALTER TABLE knowledge_candidate ADD COLUMN source_content_hash VARCHAR(64) NULL;
ALTER TABLE knowledge_candidate ADD COLUMN source_fetched_at TIMESTAMP NULL;
CREATE UNIQUE INDEX uq_knowledge_candidate_web_task ON knowledge_candidate (user_id, source_task_id);

CREATE TABLE IF NOT EXISTS web_research_page (
    task_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    url VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    excerpt TEXT NOT NULL,
    content LONGTEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    fetched_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_web_research_page_task FOREIGN KEY (task_id) REFERENCES web_research_task(id) ON DELETE CASCADE,
    INDEX idx_web_research_page_user_created (user_id, created_at)
);
