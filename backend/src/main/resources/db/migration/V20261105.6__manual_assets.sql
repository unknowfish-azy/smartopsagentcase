-- ============================================================
-- OPS-03 补完：手工登记资产
-- ============================================================
-- 背景：asset_resource 原本只由云同步写入，source_account_id 必填，
--       导致"没有云账号的资产"（自建机房、域名、中间件、K8s 集群）无法进入 CMDB。
--
-- 设计约束：
--   1. 手工资产 source='MANUAL'，source_account_id 为空，采集时间由登记时刻填充；
--   2. 可见范围不依赖云账号：按登记人 owner_user_id 或归属团队 team_id 授权；
--   3. 不改动云同步写入路径，云资产行为保持原样。

ALTER TABLE asset_resource ADD COLUMN owner_user_id BIGINT NULL;
ALTER TABLE asset_resource ADD COLUMN team_id BIGINT NULL;

CREATE INDEX ix_asset_resource_owner ON asset_resource (owner_user_id, status);
CREATE INDEX ix_asset_resource_team ON asset_resource (team_id, status);
