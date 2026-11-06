-- SEC-10 残余加固：operator_memory 缺少 (user_id, source_refs) 唯一键，
-- recordLearned/recordConfirmed 重复调用会创建同 source_refs 的重复记忆行，
-- 放大 evidence_count / confidence。先清理历史重复（保留最早一条），
-- 再把 source_refs 从 TEXT 收窄为 VARCHAR(512) 以支持跨库唯一索引
-- （H2 不支持 TEXT 前缀索引，VARCHAR 在 MySQL/H2 均可建唯一键）。

-- 1) 清理 (user_id, source_refs) 重复行：保留 created_at 最小（平局 id 最小）。
DELETE FROM operator_memory WHERE id IN (
    SELECT id FROM (
        SELECT m1.id AS id FROM operator_memory m1
        JOIN operator_memory m2
            ON m1.user_id = m2.user_id
           AND m1.source_refs IS NOT NULL
           AND m1.source_refs = m2.source_refs
        WHERE m1.created_at > m2.created_at
           OR (m1.created_at = m2.created_at AND m1.id > m2.id)
    ) duplicates
);

-- 2) 收窄列类型以便加唯一键（VARCHAR(512) utf8mb4 = 2048 字节，InnoDB 索引上限 3072）。
ALTER TABLE operator_memory MODIFY COLUMN source_refs VARCHAR(512);

-- 3) 唯一键兜底：同一用户同一 source_refs 只能有一条记忆。
--    source_refs 为 NULL 的记忆（如直接创建未填来源）不受唯一键约束。
ALTER TABLE operator_memory
    ADD CONSTRAINT uq_operator_memory_user_source_refs UNIQUE (user_id, source_refs);
