-- SmartOpsAgent training / evaluation metadata migration (D1).
-- Additive only: existing tables are not changed or removed.
--
-- 设计说明：这里只建「账本」，样本本体落数据湖（data/lake/…），表里存 URI。
-- agent_feedback 是 DPO 偏好数据的唯一来源，此前完全缺失。

CREATE TABLE IF NOT EXISTS training_dataset (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    source VARCHAR(50) NOT NULL,
    sample_count INT NOT NULL DEFAULT 0,
    storage_uri VARCHAR(500) NOT NULL,
    split VARCHAR(20) NOT NULL DEFAULT 'train',
    note VARCHAR(500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_dataset_name_split (name, split),
    KEY idx_dataset_task_type (task_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS training_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    dataset_id BIGINT NOT NULL,
    base_model VARCHAR(200) NOT NULL,
    method VARCHAR(50) NOT NULL,
    params_json JSON,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    metrics_json JSON,
    artifact_uri VARCHAR(500),
    started_at DATETIME,
    finished_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_run_dataset (dataset_id),
    KEY idx_run_status (status),
    CONSTRAINT fk_run_dataset FOREIGN KEY (dataset_id)
        REFERENCES training_dataset(id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS evaluation_run (
    id BIGINT NOT NULL AUTO_INCREMENT,
    dataset_id BIGINT NOT NULL,
    model_ref VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    metrics_json JSON,
    report_uri VARCHAR(500),
    note VARCHAR(500),
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_eval_dataset (dataset_id),
    KEY idx_eval_model (model_ref),
    CONSTRAINT fk_eval_dataset FOREIGN KEY (dataset_id)
        REFERENCES training_dataset(id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS model_registry (
    id BIGINT NOT NULL AUTO_INCREMENT,
    name VARCHAR(200) NOT NULL,
    version VARCHAR(50) NOT NULL,
    task_type VARCHAR(50) NOT NULL,
    artifact_uri VARCHAR(500) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'STAGED',
    metrics_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    promoted_at DATETIME,
    PRIMARY KEY (id),
    UNIQUE KEY uk_registry_name_version (name, version),
    KEY idx_registry_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 采纳/驳回反馈：DPO 偏好数据的来源，必须带 run_id/step_id 才能回连轨迹
CREATE TABLE IF NOT EXISTS agent_feedback (
    id BIGINT NOT NULL AUTO_INCREMENT,
    request_id VARCHAR(64),
    run_id VARCHAR(64),
    step_id VARCHAR(64),
    verdict VARCHAR(20) NOT NULL DEFAULT 'ADOPTED',
    reason VARCHAR(500),
    operator VARCHAR(100),
    payload_json JSON,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    KEY idx_feedback_run (run_id),
    KEY idx_feedback_verdict (verdict),
    KEY idx_feedback_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
