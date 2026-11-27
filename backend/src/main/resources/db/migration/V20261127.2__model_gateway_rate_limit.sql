-- 批次一 #28：模型网关限流/配额统计按 (key_id, created_at) 过滤，补复合索引。
CREATE INDEX idx_gateway_invocation_key_created ON model_gateway_invocation (key_id, created_at);
