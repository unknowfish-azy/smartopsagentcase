-- SEC-08：inspector_event 增加归属列。NULL = 内部/系统通道事件（如 agent 经内部 token 上报），
-- 普通用户读侧不可见，全局视图仅平台审计管理员可用（应用层判定）。
ALTER TABLE inspector_event ADD COLUMN user_id BIGINT;
CREATE INDEX idx_inspector_event_user ON inspector_event (user_id);

-- SEC-10：先清理 (user_id, source_type, source_ref) 重复闭环（保留最早一条：created_at 最小，平局取 id 最小），
-- 再加唯一键兜底并发 GET 的重复插入。source_ref 为 NULL 的 MANUAL 闭环不受唯一键约束（NULL 不参与唯一性）。
-- MySQL 8 不允许 DELETE 的子查询直接引用目标表（Error 1093），
-- 用派生表先物化待删 id，H2（MODE=MySQL）同样接受该写法。
DELETE FROM agent_decision_loop WHERE id IN (
    SELECT id FROM (
        SELECT d1.id AS id FROM agent_decision_loop d1
        JOIN agent_decision_loop d2
            ON d1.user_id = d2.user_id
           AND d1.source_type = d2.source_type
           AND d1.source_ref IS NOT NULL
           AND d1.source_ref = d2.source_ref
        WHERE d1.created_at > d2.created_at
           OR (d1.created_at = d2.created_at AND d1.id > d2.id)
    ) duplicates
);
ALTER TABLE agent_decision_loop ADD CONSTRAINT uq_agent_decision_loop_user_source UNIQUE (user_id, source_type, source_ref);
