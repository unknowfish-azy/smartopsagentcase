-- 告警关联事件：一次风暴折叠成一个事件，跨 task 跨 metric 关联
-- correlation_event: 主事件（风暴）
-- correlation_edge: 事件内的关联边（标注"这俩指标经常一起炸"）
-- 在线：fireAlert 触发时查最近 5 分钟同服务器 OPEN 告警，合并成一个 event
-- 离线：定时跑 lift 关联度，补 edge.lift_score 和 root_cause_alert_id

CREATE TABLE sentinel_alert_correlation (
    id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    `key` VARCHAR(120) NOT NULL UNIQUE,             -- 稳定 key，如 corr:server-1:1731200000（MySQL 保留字用反引号）
    resource_key VARCHAR(120) NOT NULL,             -- 同服务器/同 group 键
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    alert_count INT NOT NULL DEFAULT 0,
    root_cause_alert_id BIGINT NULL,                -- 事件内最早 fired_at 的告警
    root_cause_metric VARCHAR(64) NULL,
    severity VARCHAR(4) NOT NULL DEFAULT 'P2',      -- 取事件内最高 severity
    status VARCHAR(16) NOT NULL DEFAULT 'OPEN',     -- OPEN/FOLDED/RESOLVED
    metrics_affected JSON NULL,                     -- 涉及哪些指标
    task_ids JSON NULL,                             -- 涉及哪些 task
    summary VARCHAR(500) NULL,                       -- "CPU+内存+IO 同时越界"
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NULL ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_corr_resource (resource_key),
    KEY idx_corr_status_time (status, window_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE sentinel_alert_correlation_edge (
    id BIGINT NOT NULL PRIMARY KEY AUTO_INCREMENT,
    correlation_id BIGINT NOT NULL,
    alert_a_id BIGINT NOT NULL,
    alert_b_id BIGINT NOT NULL,
    metric_a VARCHAR(64) NOT NULL,
    metric_b VARCHAR(64) NOT NULL,
    co_fires INT NOT NULL DEFAULT 0,                -- 历史共同出现次数
    lift_score DOUBLE NOT NULL DEFAULT 1.0,         -- lift 关联度：>1 正相关，<1 负相关
    correlation_type VARCHAR(32) NOT NULL DEFAULT 'TIME_WINDOW',  -- TIME_WINDOW / LIFT / SAME_SERVER
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_edge_corr FOREIGN KEY (correlation_id) REFERENCES sentinel_alert_correlation(id) ON DELETE CASCADE,
    KEY idx_edge_corr (correlation_id),
    KEY idx_edge_metrics (metric_a, metric_b)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- sentinel_alert 加 correlation_id + correlation_group_key，前端可直接按 event 聚合
ALTER TABLE sentinel_alert ADD COLUMN correlation_id BIGINT NULL AFTER group_key;
ALTER TABLE sentinel_alert ADD COLUMN correlation_group VARCHAR(120) NULL AFTER correlation_id;
