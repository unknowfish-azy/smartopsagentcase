"""
GET Metrics API 测试。

覆盖：

    GET /api/servers/{serverId}/metrics
    GET /api/servers/{serverId}/metrics/latest
"""

from __future__ import annotations

import pytest


TEST_SERVER_ID = 1


def test_get_latest_metrics(
    http_client,
    require_backend,
):
    """
    测试最新指标接口。
    """
    response = http_client.get(
        (
            f"{require_backend}"
            f"/api/servers/{TEST_SERVER_ID}"
            "/metrics/latest"
        )
    )

    assert response.status_code in {
        200,
        404,
    }


def test_get_metrics(
    http_client,
    require_backend,
):
    """
    测试历史指标接口。
    """
    response = http_client.get(
        (
            f"{require_backend}"
            f"/api/servers/{TEST_SERVER_ID}"
            "/metrics"
        ),
        params={
            "page": 1,
            "size": 20,
        },
    )

    assert response.status_code in {
        200,
        404,
    }


@pytest.mark.parametrize(
    "server_id",
    [0, -1, 999999999],
)
def test_get_metrics_invalid_server(
    http_client,
    require_backend,
    server_id,
):
    """
    测试非法 / 不存在 Server ID。
    """
    response = http_client.get(
        (
            f"{require_backend}"
            f"/api/servers/{server_id}"
            "/metrics/latest"
        )
    )

    assert response.status_code in {
        400,
        404,
    }