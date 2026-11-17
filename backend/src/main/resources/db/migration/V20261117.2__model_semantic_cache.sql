-- 模型网关语义缓存（LLM 推理加速）
-- exact_hash:   精确命中（group+system+prompt+temperature 的 SHA-256）
-- semantic_hash: 归一化 prompt 的 SHA-256（同 system 上下文内的语义候选桶）
-- prompt_digest: 归一化后的 prompt 摘要，供 bigram Jaccard 相似度计算
CREATE TABLE model_semantic_cache (
    id BIGINT NOT NULL PRIMARY KEY,
    group_slug VARCHAR(120) NOT NULL,
    exact_hash CHAR(64) NOT NULL,
    semantic_hash CHAR(64) NOT NULL,
    prompt_digest VARCHAR(2000) NOT NULL,
    provider VARCHAR(120) NULL,
    model VARCHAR(120) NULL,
    content MEDIUMTEXT NOT NULL,
    input_tokens INT NULL,
    output_tokens INT NULL,
    total_tokens INT NULL,
    hit_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_hit_at TIMESTAMP NULL,
    CONSTRAINT uk_semantic_cache_exact UNIQUE (exact_hash),
    KEY idx_semantic_cache_bucket (group_slug, semantic_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
