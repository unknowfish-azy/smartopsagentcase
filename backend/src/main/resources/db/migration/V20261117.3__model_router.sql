-- 模型路由器：为 connection 声明能力标签，让网关按请求意图自动选模型
-- capabilities: JSON 数组，每个标签一个能力
--   chat          : 基础对话（所有 LLM 都有）
--   reasoning     : 深度推理（高 temperature/复杂诊断优先）
--   vision        : 图像理解（prompt 含"看图/截图/vision"时需要）
--   tool-calling  : 函数调用 / agent 工具链
--   fast          : 低延迟（简单问题优先）
--   cheap         : 低成本（默认兜底）
-- group.route_mode: AUTO 由路由器选连接，MANUAL 沿用 route 表（向后兼容）

ALTER TABLE model_connections ADD COLUMN capabilities JSON NULL AFTER model_name;
ALTER TABLE model_gateway_group ADD COLUMN route_mode VARCHAR(16) NOT NULL AFTER slug;
ALTER TABLE model_gateway_group ADD COLUMN default_capability VARCHAR(32) NULL AFTER route_mode;

-- 给已有的 DeepSeek-V4-Pro 声明能力（推理主力，视觉版）
UPDATE model_connections SET capabilities = JSON_ARRAY('chat','reasoning','vision','tool-calling')
  WHERE id = 6 AND model_name = 'deepseek-v4-pro';
-- probe5 是占位连接（模型名 'm'），只给基础能力
UPDATE model_connections SET capabilities = JSON_ARRAY('chat','fast','cheap')
  WHERE id = 1;

-- 默认 MANUAL（向后兼容），用户可在管理面板切换 AUTO
UPDATE model_gateway_group SET route_mode = 'MANUAL' WHERE route_mode IS NULL OR route_mode = '';
