"""
POST /api/servers 测试。

注意：

该测试创建测试服务器数据。

生产环境执行前应使用专门 Test Database。
"""

from __future__ import annotations

import uuid


def test_create_server(
    http_client,
    require_backend,
):
    """
    测试创建 Server。
    """
    server_name = (
        f"pytest-server-{uuid.uuid4().hex[:8]}"
    )

    payload = {
        "name": server_name,
        "host": "127.0.0.1",
        "port": 22,
        "description": "Pytest test server",
    }

    response = http_client.post(
        f"{require_backend}/api/servers",
        json=payload,
    )

    assert response.status_code in {
        200,
        201,
    }

    data = response.json()

    assert isinstance(
        data,
        dict,
    )


def test_create_server_invalid_payload(
    http_client,
    require_backend,
):
    """
    测试非法创建参数。
    """
    response = http_client.post(
        f"{require_backend}/api/servers",
        json={},
    )

    assert response.status_code in {
        400,
        422,
    }


def test_create_server_invalid_port(
    http_client,
    require_backend,
):
    """
    测试非法 SSH Port。
    """
    payload = {
        "name": "pytest-invalid-port",
        "host": "127.0.0.1",
        "port": -1,
    }

    response = http_client.post(
        f"{require_backend}/api/servers",
        json=payload,
    )

    assert response.status_code in {
        400,
        422,
    }