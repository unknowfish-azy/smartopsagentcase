-- ============================================================
-- SEC-08：服务器资产归属列（过渡期属主模型）
-- ============================================================
-- 历史上 server 是全局表，任意登录用户可读全部资产。
-- 新增 owner_id 后创建即归属创建者；历史行 owner_id 为 NULL，
-- 仅具备 admin.audit 的平台审计管理员可读（全局视图，应用层留审计）。
-- inspector_event 的归属列由 V20261106.20 统一提供（user_id）。

ALTER TABLE server ADD COLUMN owner_id BIGINT NULL;
CREATE INDEX ix_server_owner ON server(owner_id);
