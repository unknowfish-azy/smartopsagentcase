INSERT INTO server
(
    name,
    host,
    port,
    os,
    status,
    description,
    created_at,
    updated_at
)
VALUES
    (
        'Test-Server-01',
        '127.0.0.1',
        22,
        'Ubuntu 24.04',
        'ONLINE',
        '测试服务器',
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    );

INSERT INTO server_metric
(
    server_id,
    cpu_usage,
    memory_usage,
    disk_usage,
    network_in,
    network_out,
    load_average,
    status,
    collected_at
)
VALUES
    (
        1,
        35.5,
        52.2,
        61.3,
        10.5,
        8.2,
        0.72,
        'NORMAL',
        CURRENT_TIMESTAMP
    );