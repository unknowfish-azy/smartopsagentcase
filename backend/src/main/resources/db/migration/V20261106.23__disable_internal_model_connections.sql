-- SEC-14 残余：存量 model_connections 中可能存在指向内网地址的 base_url。
-- OutboundUrlPolicy 在 runtime/invoke 时会拒绝这些地址（400），但用户仍能在列表中
-- 看到"可用"的连接。本迁移主动禁用指向常见内网地址的存量连接。
--
-- 注意：纯 SQL 无法做 DNS 解析，因此本迁移只覆盖字面量内网 IP / localhost。
-- 指向内网的 DNS 名（如 internal.service.local）无法被 SQL 识别，调用时仍由
-- OutboundUrlPolicy.inspect 做 DNS 解析后拒绝（400 BASE_URL_INVALID）。

UPDATE model_connections
SET enabled = FALSE,
    updated_at = CURRENT_TIMESTAMP
WHERE enabled = TRUE
  AND base_url REGEXP '://(localhost|127\\.[0-9.]+|10\\.[0-9.]+|192\\.168\\.[0-9.]+|169\\.254\\.[0-9.]+|0\\.0\\.0\\.0|\\[::1\\]|172\\.(1[6-9]|2[0-9]|3[01])\\.[0-9.]+)';
