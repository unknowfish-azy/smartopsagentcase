-- Flyway 保证该脚本只执行一次，使用 MySQL/H2 都支持的标准语法。
ALTER TABLE personal_knowledge_library ADD COLUMN storage_slug VARCHAR(160);
ALTER TABLE personal_knowledge_library ADD COLUMN storage_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE personal_knowledge_entry ADD COLUMN entry_relative_path VARCHAR(512);
ALTER TABLE personal_knowledge_entry ADD COLUMN content_hash VARCHAR(64);
ALTER TABLE personal_knowledge_entry ADD COLUMN index_status VARCHAR(32) NOT NULL DEFAULT 'PENDING';
ALTER TABLE personal_knowledge_entry ADD COLUMN index_error VARCHAR(1000);
