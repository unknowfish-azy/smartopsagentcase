"""
GET /api/servers 测试。

覆盖：

    GET /api/servers
    GET /api/servers/{id}
"""

from __future__ import annotations

import pytest


def test_get_servers(
    http_client,
    require_backend,
):
    """
    测试服务器列表接口。
    """
    response = http_client.get(
        f"{require_backend}/api/servers"
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(
        data,
        dict,
    )


def test_get_server_not_found(
    http_client,
    require_backend,
):
    """
    使用一个极大 ID 测试不存在服务器的处理。

    这里允许后端返回：

        404
        400

    具体取决于当前 Controller 设计。
    """
    response = http_client.get(
        (
            f"{require_backend}"
            "/api/servers/999999999"
        )
    )

    assert response.status_code in {
        400,
        404,
    }


@pytest.mark.parametrize(
    "page,size",
    [
        (1, 10),
        (1, 20),
        (1, 50),
    ],
)
def test_get_servers_pagination(
    http_client,
    require_backend,
    page,
    size,
):
    """
    测试分页参数。
    """
    response = http_client.get(
        f"{require_backend}/api/servers",
        params={
            "page": page,
            "size": size,
        },
    )

    assert response.status_code in {
        200,
        400,
    }