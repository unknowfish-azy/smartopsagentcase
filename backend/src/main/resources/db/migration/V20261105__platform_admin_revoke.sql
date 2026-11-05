-- 平台管理员撤销改为“保留档案 + 标记撤销时间”：
-- 原实现直接删除 platform_admin_profile，会让该账号命中“无档案=历史管理员”的历史语义而被重新放行。
ALTER TABLE platform_admin_profile ADD COLUMN revoked_at TIMESTAMP NULL;
