-- ============================================================
-- OPS-02 / OPS-03：多云只读接入 + 轻量 CMDB
-- ============================================================
-- 设计约束：
--   1. 凭据不落本表：cloud_account 只保存 credential_ref（credential:<id> 或 env:<NAME>），
--      明文密钥仍在 operation_credential / 环境变量中，接口输出永不含密钥。
--   2. 资源身份稳定：resource_uid = provider:accountId:region:type:providerResourceId，
--      同一资源重复同步走 UPDATE，不重复建档。
--   3. 状态可区分：ACTIVE（最近一次成功同步命中）、MISSING（成功全量同步中消失）、
--      DELETED（显式标记，附证据）、STALE（读取时按采集新鲜度计算，不落库改写）。
--   4. 关系保留依据：asset_relation.source 区分 DECLARED / DERIVED，evidence 必填，
--      业务影响视图直接引用该依据，不做无来源推断。

CREATE TABLE IF NOT EXISTS cloud_account (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    provider VARCHAR(32) NOT NULL,
    account_id VARCHAR(128) NOT NULL,
    display_name VARCHAR(160) NOT NULL,
    region VARCHAR(64) NOT NULL,
    endpoint VARCHAR(255),
    project_id VARCHAR(128),
    team_id BIGINT,
    owner_user_id BIGINT NOT NULL,
    credential_ref VARCHAR(255) NOT NULL,
    credential_scope VARCHAR(32) NOT NULL DEFAULT 'READ_ONLY',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_sync_at DATETIME,
    last_sync_status VARCHAR(24),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uk_cloud_account_identity UNIQUE (provider, account_id, region)
);

CREATE INDEX ix_cloud_account_owner ON cloud_account (owner_user_id, id);
CREATE INDEX ix_cloud_account_team ON cloud_account (team_id, id);

CREATE TABLE IF NOT EXISTS cloud_sync_run (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    actor_user_id BIGINT,
    status VARCHAR(24) NOT NULL,
    started_at DATETIME NOT NULL,
    ended_at DATETIME,
    pages INT NOT NULL DEFAULT 0,
    discovered INT NOT NULL DEFAULT 0,
    created_count INT NOT NULL DEFAULT 0,
    updated_count INT NOT NULL DEFAULT 0,
    marked_missing INT NOT NULL DEFAULT 0,
    permission_denied BOOLEAN NOT NULL DEFAULT FALSE,
    error_code VARCHAR(64),
    error_message VARCHAR(500)
);

CREATE INDEX ix_cloud_sync_run_account ON cloud_sync_run (account_id, started_at);

CREATE TABLE IF NOT EXISTS asset_resource (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    resource_uid VARCHAR(200) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    provider_account_id VARCHAR(128) NOT NULL,
    region VARCHAR(64) NOT NULL,
    resource_type VARCHAR(32) NOT NULL,
    provider_resource_id VARCHAR(160) NOT NULL,
    name VARCHAR(255) NOT NULL,
    status VARCHAR(24) NOT NULL,
    status_reason VARCHAR(500),
    environment VARCHAR(64),
    business VARCHAR(128),
    owner VARCHAR(160),
    source VARCHAR(32) NOT NULL DEFAULT 'CLOUD_SYNC',
    source_account_id BIGINT,
    -- 增量同步记账：本次同步是否命中该资源，用于精确判定 MISSING（不依赖时间戳精度）
    last_sync_run_id BIGINT,
    collected_at DATETIME NOT NULL,
    first_seen_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL,
    tags_json TEXT,
    metadata_json TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uk_asset_resource_uid UNIQUE (resource_uid)
);

CREATE INDEX ix_asset_resource_business ON asset_resource (business, environment, resource_type, status);
CREATE INDEX ix_asset_resource_account ON asset_resource (source_account_id, status);

CREATE TABLE IF NOT EXISTS asset_relation (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    from_uid VARCHAR(200) NOT NULL,
    to_uid VARCHAR(200) NOT NULL,
    relation_type VARCHAR(48) NOT NULL,
    source VARCHAR(16) NOT NULL,
    evidence VARCHAR(500) NOT NULL,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT uk_asset_relation_edge UNIQUE (from_uid, to_uid, relation_type)
);

CREATE INDEX ix_asset_relation_from ON asset_relation (from_uid, relation_type);
CREATE INDEX ix_asset_relation_to ON asset_relation (to_uid, relation_type);
