"""
Pytest 公共 Fixture。

作用：

    - 统一读取环境变量
    - 统一 API Base URL
    - 统一 AI Service URL
    - 统一 Knowledge Service URL
    - 统一 MySQL / Redis 配置
    - 提供 HTTP Client
    - 没启动服务时自动 skip
"""

from __future__ import annotations

import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest


@pytest.fixture
def tmp_path() -> Path:
    """Use a project-local disposable directory when Windows temp ACLs are restricted."""
    root = Path(__file__).resolve().parent / ".pytest-runtime"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"case-{uuid.uuid4().hex}"
    path.mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


# ============================================================
# Configuration
# ============================================================


@dataclass
class TestConfig:
    """
    测试环境配置。
    """

    backend_url: str = "http://127.0.0.1:8080"

    ai_service_url: str = "http://127.0.0.1:8001"

    knowledge_service_url: str = "http://127.0.0.1:8002"

    mysql_host: str = "127.0.0.1"

    mysql_port: int = 3306

    mysql_user: str = "root"

    mysql_password: str = ""

    mysql_database: str = "smartops"

    redis_host: str = "127.0.0.1"

    redis_port: int = 6379

    redis_db: int = 0

    @classmethod
    def from_env(cls) -> "TestConfig":
        return cls(
            backend_url=os.getenv(
                "SMARTOPS_BACKEND_URL",
                cls.backend_url,
            ),
            ai_service_url=os.getenv(
                "SMARTOPS_AI_SERVICE_URL",
                cls.ai_service_url,
            ),
            knowledge_service_url=os.getenv(
                "SMARTOPS_KNOWLEDGE_SERVICE_URL",
                cls.knowledge_service_url,
            ),
            mysql_host=os.getenv(
                "SMARTOPS_MYSQL_HOST",
                cls.mysql_host,
            ),
            mysql_port=int(
                os.getenv(
                    "SMARTOPS_MYSQL_PORT",
                    str(cls.mysql_port),
                )
            ),
            mysql_user=os.getenv(
                "SMARTOPS_MYSQL_USER",
                cls.mysql_user,
            ),
            mysql_password=os.getenv(
                "SMARTOPS_MYSQL_PASSWORD",
                cls.mysql_password,
            ),
            mysql_database=os.getenv(
                "SMARTOPS_MYSQL_DATABASE",
                cls.mysql_database,
            ),
            redis_host=os.getenv(
                "SMARTOPS_REDIS_HOST",
                cls.redis_host,
            ),
            redis_port=int(
                os.getenv(
                    "SMARTOPS_REDIS_PORT",
                    str(cls.redis_port),
                )
            ),
            redis_db=int(
                os.getenv(
                    "SMARTOPS_REDIS_DB",
                    str(cls.redis_db),
                )
            ),
        )


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture(scope="session")
def test_config() -> TestConfig:
    """
    返回统一测试配置。
    """
    return TestConfig.from_env()


@pytest.fixture
def http_client() -> httpx.Client:
    """
    同步 HTTP Client。

    测试结束自动关闭。
    """
    client = httpx.Client(
        timeout=10.0,
        follow_redirects=False,
    )

    try:
        yield client
    finally:
        client.close()


# ============================================================
# Service Helpers
# ============================================================


def service_available(
    client: httpx.Client,
    url: str,
) -> bool:
    """
    判断 HTTP Service 是否可访问。
    """
    try:
        response = client.get(url)
        return response.status_code < 500
    except httpx.HTTPError:
        return False


@pytest.fixture
def require_backend(
    http_client: httpx.Client,
    test_config: TestConfig,
) -> str:
    """
    Backend 不可用时跳过测试。
    """
    health_url = (
        f"{test_config.backend_url}"
        "/actuator/health"
    )

    if not service_available(
        http_client,
        health_url,
    ):
        pytest.skip(
            (
                "Spring Boot Backend 未启动："
                f"{test_config.backend_url}"
            )
        )

    return test_config.backend_url


@pytest.fixture
def require_ai_service(
    http_client: httpx.Client,
    test_config: TestConfig,
) -> str:
    """
    AI Service 不可用时跳过。
    """
    health_url = (
        f"{test_config.ai_service_url}"
        "/api/health"
    )

    if not service_available(
        http_client,
        health_url,
    ):
        pytest.skip(
            (
                "AI Service 未启动："
                f"{test_config.ai_service_url}"
            )
        )

    return test_config.ai_service_url


@pytest.fixture
def require_knowledge_service(
    http_client: httpx.Client,
    test_config: TestConfig,
) -> str:
    """
    Knowledge Service 不可用时跳过。
    """
    health_url = (
        f"{test_config.knowledge_service_url}"
        "/api/health"
    )

    if not service_available(
        http_client,
        health_url,
    ):
        pytest.skip(
            (
                "Knowledge Service 未启动："
                f"{test_config.knowledge_service_url}"
            )
        )

    return test_config.knowledge_service_url
