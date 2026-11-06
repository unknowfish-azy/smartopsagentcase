-- ============================================================
-- OPS-14：容量趋势、闲置/超配分析、标签成本归集、预算与成本异常
-- ============================================================
-- 原则：
--   1. 金额以最小货币单位（分/厘）存 BIGINT，避免浮点误差；币种独立汇总，绝不跨币种相加；
--   2. 每条成本必须带账单来源（source_id）与账期；没有标签的记录归为 UNALLOCATED，不猜测归属；
--   3. 利用率样本只存观测值（0..100），建议必须带采样窗口与样本数，样本不足不产出规格建议；
--   4. 预算与异常基于真实账期数据，缺上期数据时不做增长率推断。
-- 全部语句幂等。

CREATE TABLE IF NOT EXISTS finops_cost_record (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  source_id       VARCHAR(128) NOT NULL,
  resource_id     VARCHAR(200) NOT NULL,
  resource_name   VARCHAR(200) NULL,
  provider        VARCHAR(64)  NULL,
  region          VARCHAR(64)  NULL,
  billing_month   VARCHAR(7)   NOT NULL,
  amount_minor    BIGINT       NOT NULL,
  currency        VARCHAR(3)   NOT NULL,
  allocation_key  VARCHAR(200) NULL,
  tags_json       TEXT         NULL,
  ingested_at     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_finops_cost (user_id, source_id, resource_id, billing_month, currency),
  KEY idx_finops_cost_period (user_id, billing_month),
  KEY idx_finops_cost_resource (user_id, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS finops_usage_sample (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  resource_id     VARCHAR(200) NOT NULL,
  sampled_at      DATETIME     NOT NULL,
  cpu_percent     DOUBLE       NULL,
  memory_percent  DOUBLE       NULL,
  disk_percent    DOUBLE       NULL,
  source          VARCHAR(128) NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uk_finops_usage (user_id, resource_id, sampled_at),
  KEY idx_finops_usage_window (user_id, resource_id, sampled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS finops_budget (
  id              BIGINT       NOT NULL AUTO_INCREMENT,
  user_id         BIGINT       NOT NULL,
  name            VARCHAR(128) NOT NULL,
  billing_month   VARCHAR(7)   NOT NULL,
  currency        VARCHAR(3)   NOT NULL,
  amount_minor    BIGINT       NOT NULL,
  allocation_key  VARCHAR(200) NULL,
  created_at      DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_finops_budget (user_id, name, billing_month),
  KEY idx_finops_budget_period (user_id, billing_month)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
