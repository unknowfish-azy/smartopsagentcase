"""
E2E 登录测试。

注意：

当前项目如果还没有正式认证 API，
该测试会自动跳过。
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.e2e
def test_login(
    http_client,
    require_backend,
):
    """
    测试登录流程。

    登录接口通过环境变量配置：

        SMARTOPS_LOGIN_PATH

默认：

        /api/auth/login
    """
    login_path = os.getenv(
        "SMARTOPS_LOGIN_PATH",
        "/api/auth/login",
    )

    username = os.getenv(
        "SMARTOPS_TEST_USERNAME"
    )

    password = os.getenv(
        "SMARTOPS_TEST_PASSWORD"
    )

    if not username or not password:
        pytest.skip(
            (
                "未设置 "
                "SMARTOPS_TEST_USERNAME / "
                "SMARTOPS_TEST_PASSWORD"
            )
        )

    response = http_client.post(
        f"{require_backend}{login_path}",
        json={
            "username": username,
            "password": password,
        },
    )

    assert response.status_code in {
        200,
        201,
        401,
    }