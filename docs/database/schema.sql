CREATE DATABASE IF NOT EXISTS smartops
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smartops;


CREATE TABLE IF NOT EXISTS server (
    id BIGINT NOT NULL AUTO_INCREMENT,

    name VARCHAR(100) NOT NULL,

    host VARCHAR(255) NOT NULL,

    port INT NOT NULL DEFAULT 22,

    os VARCHAR(100),

    status VARCHAR(20) NOT NULL DEFAULT 'UNKNOWN',

    description VARCHAR(500),

    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_server_name (name),

    KEY idx_server_status (status),

    KEY idx_server_host (host)
)
ENGINE=InnoDB
DEFAULT CHARSET=utf8mb4
COLLATE=utf8mb4_unicode_ci;


CREATE TABLE IF NOT EXISTS server_metric (
    id BIGINT NOT NULL AUTO_INCREMENT,

    server_id BIGINT NOT NULL,

    cpu_usage DOUBLE,

    memory_usage DOUBLE,

    disk_usage DOUBLE,

    network_in DOUBLE,

    network_out DOUBLE,

    load_average DOUBLE,

    status VARCHAR(20) NOT NULL DEFAULT 'NORMAL',

    collected_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    KEY idx_metric_server_id (server_id),

    KEY idx_metric_collected_at (collected_at),

    KEY idx_metric_server_time (
        server_id,
        collected_at
    ),

    CONSTRAINT fk_metric_server
        FOREIGN KEY (server_id)
        REFERENCES server(id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
);