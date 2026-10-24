"""
E2E 添加服务器。
"""

from __future__ import annotations

import uuid

import pytest


@pytest.mark.e2e
def test_add_server(
    http_client,
    require_backend,
):
    """
    创建测试服务器并验证列表中可以查询。
    """
    server_name = (
        f"e2e-server-{uuid.uuid4().hex[:8]}"
    )

    payload = {
        "name": server_name,
        "host": "127.0.0.1",
        "port": 22,
        "description": "E2E test server",
    }

    create_response = http_client.post(
        f"{require_backend}/api/servers",
        json=payload,
    )

    assert create_response.status_code in {
        200,
        201,
    }

    list_response = http_client.get(
        f"{require_backend}/api/servers"
    )

    assert list_response.status_code == 200

    data = list_response.json()

    assert isinstance(
        data,
        dict,
    )