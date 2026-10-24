CREATE TABLE IF NOT EXISTS model_gateway_key (
  id BIGINT PRIMARY KEY,
  owner_user_id BIGINT NOT NULL,
  name VARCHAR(120) NOT NULL,
  key_prefix VARCHAR(24) NOT NULL,
  key_hash CHAR(64) NOT NULL UNIQUE,
  scope VARCHAR(20) NOT NULL DEFAULT 'PERSONAL',
  expires_at TIMESTAMP NULL,
  revoked_at TIMESTAMP NULL,
  request_limit_24h BIGINT NULL,
  token_limit_24h BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gateway_key_owner (owner_user_id),
  INDEX idx_gateway_key_prefix (key_prefix)
);
CREATE TABLE IF NOT EXISTS model_gateway_group (
  id BIGINT PRIMARY KEY,
  owner_user_id BIGINT NULL,
  name VARCHAR(120) NOT NULL,
  slug VARCHAR(120) NOT NULL UNIQUE,
  scope VARCHAR(20) NOT NULL DEFAULT 'PERSONAL',
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  request_limit_24h BIGINT NULL,
  token_limit_24h BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS model_gateway_route (
  id BIGINT PRIMARY KEY,
  group_id BIGINT NOT NULL,
  connection_id BIGINT NOT NULL,
  priority INT NOT NULL DEFAULT 100,
  weight INT NOT NULL DEFAULT 100,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  failure_count INT NOT NULL DEFAULT 0,
  unhealthy_until TIMESTAMP NULL,
  last_checked_at TIMESTAMP NULL,
  last_error_code VARCHAR(40) NULL,
  FOREIGN KEY (group_id) REFERENCES model_gateway_group(id),
  INDEX idx_gateway_route_group (group_id, enabled, priority)
);
CREATE TABLE IF NOT EXISTS model_gateway_invocation (
  id BIGINT PRIMARY KEY,
  key_id BIGINT NULL,
  group_slug VARCHAR(120) NOT NULL,
  model_name VARCHAR(160) NULL,
  status VARCHAR(24) NOT NULL,
  duration_ms BIGINT NULL,
  input_tokens BIGINT NULL,
  output_tokens BIGINT NULL,
  total_tokens BIGINT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_gateway_invocation_created (created_at),
  INDEX idx_gateway_invocation_group (group_slug)
);
