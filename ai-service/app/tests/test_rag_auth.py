import pytest

from app.core.config import settings
from app.services.rag import RAGService


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "query": "q",
            "results": [],
            "evidences": [],
            "citations": [],
            "trust_score": 0.0,
        }


class FakeClient:
    last_headers = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json, headers):
        assert url.endswith("/api/search")
        FakeClient.last_headers = headers
        return FakeResponse()


@pytest.mark.asyncio
async def test_rag_forwards_api_key_to_knowledge(monkeypatch):
    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "knowledge_api_key", "s3cret")

    result = await RAGService().retrieve("nginx")

    assert FakeClient.last_headers == {"X-API-Key": "s3cret"}
    assert result["retrieval_status"] == "empty"
    assert result["degraded"] is False


@pytest.mark.asyncio
async def test_rag_sends_no_key_when_knowledge_auth_is_off(monkeypatch):
    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "knowledge_api_key", "")

    await RAGService().retrieve("nginx")

    assert FakeClient.last_headers == {}


@pytest.mark.asyncio
async def test_rag_forwards_correlation_ids_to_knowledge(monkeypatch):
    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "knowledge_api_key", "")

    await RAGService().retrieve(
        "nginx",
        request_id="req-rag-1",
        task_id="task-rag-1",
        run_id="run-rag-1",
    )

    assert FakeClient.last_headers == {
        "X-Request-ID": "req-rag-1",
        "X-Task-ID": "task-rag-1",
        "X-Run-ID": "run-rag-1",
    }
