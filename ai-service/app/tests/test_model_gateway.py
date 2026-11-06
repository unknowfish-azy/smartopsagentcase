import pytest

from app.services.model_gateway import ModelGateway


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "connectionId": 9,
            "provider": "openai-compatible",
            "model": "ops-model",
            "content": "healthy",
            "usage": {"total_tokens": 4},
        }


class FakeClient:
    last_call = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, *, headers, json, **kwargs):
        FakeClient.last_call = (url, headers, json)
        return FakeResponse()


@pytest.mark.asyncio
async def test_gateway_uses_backend_credential_proxy(monkeypatch):
    monkeypatch.setattr(
        "app.services.model_gateway.httpx.AsyncClient",
        FakeClient,
    )
    gateway = ModelGateway(
        backend_url="http://backend:8080",
        internal_token="internal-test-token",
    )

    result = await gateway.chat(
        connection_id=9,
        user_id=3,
        prompt="status",
    )

    url, headers, payload = FakeClient.last_call
    assert url.endswith("/api/model-connections/9/invoke")
    assert headers["X-SmartOps-Internal-Token"] == "internal-test-token"
    assert "apiKey" not in payload
    assert result["content"] == "healthy"
