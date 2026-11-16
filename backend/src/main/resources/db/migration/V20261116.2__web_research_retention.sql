-- T35a/T35b：增量索引 + 快照保留 + 调度竞争 claim。
-- 索引支撑"同 URL 上一版"查询（diffCrawlPage 相邻快照 / persist 的 lastHash 比对），避免全表扫。
-- 注意：web_research_page 主键是 task_id（一任务一快照），没有 id 列。
CREATE INDEX idx_web_research_page_user_url_task ON web_research_page (user_id, url, task_id);
CREATE INDEX idx_knowledge_crawl_page_source_url_id ON knowledge_crawl_page (source_id, user_id, url, id);

-- 调度竞争：条件更新领取（claim_token 非空且未过期为已被领取）；租约超时按 UNCERTAIN 语义处理。
ALTER TABLE knowledge_crawl_source ADD COLUMN claim_token VARCHAR(64) NULL;
ALTER TABLE knowledge_crawl_source ADD COLUMN claim_expiry TIMESTAMP NULL;
