"""
Spring Boot Integration Test.

检查：

    Spring Boot
        ↓
    Actuator Health
        ↓
    API
"""

from __future__ import annotations



def test_spring_boot_health(
    http_client,
    require_backend,
):
    """
    测试 Spring Boot Actuator。
    """
    response = http_client.get(
        f"{require_backend}/actuator/health"
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(
        data,
        dict,
    )

    assert (
        data.get("status")
        in {
            "UP",
            "DOWN",
        }
    )


def test_spring_boot_anonymous_server_api(http_client, require_backend):
    """Protected controller rejects anonymous access; health remains public."""
    response = http_client.get(f"{require_backend}/api/servers")
    assert response.status_code == 401
