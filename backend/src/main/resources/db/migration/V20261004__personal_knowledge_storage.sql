ALTER TABLE personal_knowledge_library ADD COLUMN IF NOT EXISTS storage_slug VARCHAR(160);
ALTER TABLE personal_knowledge_library ADD COLUMN IF NOT EXISTS storage_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE personal_knowledge_entry ADD COLUMN IF NOT EXISTS entry_relative_path VARCHAR(512);
ALTER TABLE personal_knowledge_entry ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64);
ALTER TABLE personal_knowledge_entry ADD COLUMN IF NOT EXISTS index_status VARCHAR(32) NOT NULL DEFAULT 'PENDING';
ALTER TABLE personal_knowledge_entry ADD COLUMN IF NOT EXISTS index_error VARCHAR(1000);
