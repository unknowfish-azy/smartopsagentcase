"""PERF-02：共享 HTTP transport、并发闸门与过载语义的回归测试。"""
import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.exceptions import UpstreamSaturated
from app.core.http_pool import HttpPool, http_pool
from app.main import ai_service_exception_handler, app
from app.services.model_gateway import ModelGateway


@pytest.mark.asyncio
async def test_shared_pool_reuses_one_client_for_100_concurrent_borrows():
    pool = HttpPool(
        max_connections=8,
        max_keepalive_connections=4,
        max_concurrent_requests=8,
        queue_timeout=5.0,
    )
    await pool.startup()
    try:
        async def borrow() -> None:
            async with pool.acquire() as client:
                assert isinstance(client, httpx.AsyncClient)
                await asyncio.sleep(0.005)

        await asyncio.gather(*(borrow() for _ in range(100)))

        snapshot = pool.snapshot()
        # 100 个并发借出只创建 1 个客户端：握手/连接池建立次数可观测且不随请求增长。
        assert snapshot["clientCreations"] == 1
        assert snapshot["saturated"] == 0
        assert snapshot["gateWaits"] == 100
        assert snapshot["inFlight"] == 0
    finally:
        await pool.shutdown()


@pytest.mark.asyncio
async def test_gate_rejects_with_explicit_overload():
    pool = HttpPool(max_concurrent_requests=1, queue_timeout=0.05)
    await pool.startup()
    try:
        async with pool.acquire():
            with pytest.raises(UpstreamSaturated) as error:
                async with pool.acquire():
                    pass

        assert error.value.code == "UPSTREAM_SATURATED"
        assert error.value.http_status == 503
        assert error.value.headers["Retry-After"]
        assert pool.snapshot()["saturated"] == 1
        assert pool.snapshot()["inFlight"] == 0
    finally:
        await pool.shutdown()


@pytest.mark.asyncio
async def test_overload_maps_to_503_with_explicit_code():
    response = await ai_service_exception_handler(None, UpstreamSaturated("上游容量已饱和"))
    assert response.status_code == 503
    assert json.loads(response.body)["code"] == "UPSTREAM_SATURATED"
    assert response.headers["Retry-After"] == "2"


def test_lifespan_creates_and_closes_the_shared_client(monkeypatch):
    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            created.append(kwargs)
            assert kwargs["trust_env"] is False
            self.closed = False

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr("app.core.http_pool.httpx.AsyncClient", FakeClient)

    assert http_pool.snapshot()["shared"] is False
    with TestClient(app):
        assert http_pool.snapshot()["shared"] is True
        assert http_pool.snapshot()["clientCreations"] == 1
        assert len(created) == 1
        # 连接预算来自配置，实际值可观测。
        assert http_pool.snapshot()["maxConnections"] > 0

    assert http_pool.snapshot()["shared"] is False


@pytest.mark.asyncio
async def test_concurrent_gateway_calls_keep_credentials_and_results_isolated(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            return None

        def json(self):
            return {"content": self.content}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, headers, json, **kwargs):
            calls.append((headers["X-User-Id"], json["prompt"]))
            await asyncio.sleep(0.01)
            return FakeResponse(f"answer-for-{headers['X-User-Id']}")

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    gateway = ModelGateway(backend_url="http://backend:8080", internal_token="internal-token")

    first, second = await asyncio.gather(
        gateway.chat(connection_id=9, user_id=1, prompt="first"),
        gateway.chat(connection_id=9, user_id=2, prompt="second"),
    )

    assert first["content"] == "answer-for-1"
    assert second["content"] == "answer-for-2"
    assert sorted(calls) == [("1", "first"), ("2", "second")]
