-- 聊天反馈 → Agent 独立复核 → 待审核候选 → 审核通过后全局共享知识
-- 隔离口径：反馈与候选仍按 user_id 隔离；只有 promote 后的共享条目全员只读可见。

CREATE TABLE IF NOT EXISTS chat_feedback (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    message_id VARCHAR(64) NOT NULL,
    prompt TEXT NOT NULL,
    original_answer LONGTEXT NOT NULL,
    issue_type VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    expected TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'REVIEWING',
    review_conclusion VARCHAR(32),
    revision LONGTEXT,
    provider_key VARCHAR(64),
    citations_json LONGTEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uq_chat_feedback_message (user_id, message_id),
    INDEX idx_chat_feedback_user_status (user_id, status, created_at)
);

-- 反馈候选关联（source_run_id / source_task_id 均可空，沿用既有候选表）
ALTER TABLE knowledge_candidate ADD COLUMN source_message_id VARCHAR(64) NULL;
CREATE UNIQUE INDEX uq_knowledge_candidate_message ON knowledge_candidate (user_id, source_message_id);

-- 审核通过后的全局只读共享知识（不继承 user_id，全员可见；仅管理员/审核员可写）
CREATE TABLE IF NOT EXISTS shared_knowledge_entry (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    candidate_id BIGINT NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT,
    content_markdown LONGTEXT NOT NULL,
    citations_json LONGTEXT,
    source_type VARCHAR(32) NOT NULL,
    published_by BIGINT NOT NULL,
    published_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_shared_knowledge_candidate (candidate_id),
    INDEX idx_shared_knowledge_published (published_at DESC)
);
