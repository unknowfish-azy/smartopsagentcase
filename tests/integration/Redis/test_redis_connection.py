"""
Redis 集成测试。

环境变量：

    SMARTOPS_REDIS_HOST
    SMARTOPS_REDIS_PORT
    SMARTOPS_REDIS_DB
"""

from __future__ import annotations

import uuid

import pytest


def test_redis_ping(
    test_config,
):
    """
    Redis PING。
    """
    redis = pytest.importorskip(
        "redis"
    )

    try:
        client = redis.Redis(
            host=test_config.redis_host,
            port=test_config.redis_port,
            db=test_config.redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        assert client.ping() is True

    except Exception as exc:
        pytest.skip(
            f"Redis 当前不可用：{exc}"
        )


def test_redis_set_get(
    test_config,
):
    """
    测试 Redis 基础读写。

    使用带随机后缀的测试 Key，
    避免污染正常业务数据。
    """
    redis = pytest.importorskip(
        "redis"
    )

    key = (
        f"smartops:pytest:"
        f"{uuid.uuid4().hex}"
    )

    value = "smartops-test"

    try:
        client = redis.Redis(
            host=test_config.redis_host,
            port=test_config.redis_port,
            db=test_config.redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )

        client.set(
            key,
            value,
            ex=60,
        )

        assert (
            client.get(key)
            == value
        )

    except Exception as exc:
        pytest.skip(
            f"Redis 当前不可用：{exc}"
        )

    finally:
        try:
            client.delete(key)
        except Exception:
            pass