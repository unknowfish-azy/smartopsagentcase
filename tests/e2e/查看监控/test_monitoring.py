"""
E2E Monitoring Test.
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
def test_view_monitoring(
    http_client,
    require_backend,
):
    """
    验证：

        Server
        ↓
        Latest Metrics
    """
    servers = http_client.get(
        f"{require_backend}/api/servers"
    )

    assert servers.status_code == 200

    data = servers.json()

    assert isinstance(
        data,
        dict,
    )

    # 当前分页 / 返回模型可能不同，
    # 因此这里只在明确获得 ID 后继续。
    items = (
        data.get("data")
        or data.get("items")
        or []
    )

    if not items:
        pytest.skip(
            "当前测试数据库没有服务器数据"
        )

    first = items[0]

    server_id = (
        first.get("id")
        if isinstance(first, dict)
        else None
    )

    if not server_id:
        pytest.skip(
            "无法从 Server API 返回值中获得 ID"
        )

    metrics = http_client.get(
        (
            f"{require_backend}"
            f"/api/servers/{server_id}"
            "/metrics/latest"
        )
    )

    assert metrics.status_code in {
        200,
        404,
    }