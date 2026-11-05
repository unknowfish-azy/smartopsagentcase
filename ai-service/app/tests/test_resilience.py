"""Behavior regressions for unavailable retrieval and interrupted real output."""
import json

import httpx
import pytest

from app.core.config import settings
from app.core.exceptions import LLMException
from app.schemas.chat import ChatRequest
from app.services.chat import ChatService
from app.services.llm import LLMService
from app.services.rag import RAGService


def knowledge_transport(monkeypatch, *, payload=None, status=200, broken_json=False, offline=False):
    """Replace the external HTTP transport, retaining real client/proxy handling."""
    real_client = httpx.AsyncClient

    def respond(request):
        if offline:
            raise httpx.ConnectError("test offline", request=request)
        if broken_json:
            return httpx.Response(status, content=b"not JSON")
        return httpx.Response(status, json=payload)

    def client(**kwargs):
        # A proxy inherited here would bypass MockTransport as well as the local service.
        assert kwargs.get("trust_env") is False
        return real_client(**kwargs, transport=httpx.MockTransport(respond))

    monkeypatch.setattr(httpx, "AsyncClient", client)


@pytest.mark.asyncio
@pytest.mark.parametrize("kwargs,expected", [
    ({"offline": True}, "unavailable"),
    ({"status": 503}, "unavailable"),
    ({"broken_json": True}, "invalid_response"),
    ({"payload": []}, "invalid_response"),
    ({"payload": {"results": "bad"}}, "invalid_response"),
    ({"payload": {"results": ["bad"]}}, "invalid_response"),
    ({"payload": {"results": [], "trust_score": "bad"}}, "invalid_response"),
    ({"payload": {"results": [], "trust_score": "Infinity"}}, "invalid_response"),
    ({"payload": {"results": [], "citations": [{"score": "NaN"}]}}, "invalid_response"),
    ({"payload": {"results": [], "citations": [{"score": "Infinity"}]}}, "invalid_response"),
    ({"payload": {"results": [], "evidences": [{"content": "guide", "score": "bad"}]}}, "invalid_response"),
    ({"payload": {"results": [], "evidences": [{"content": "guide", "score": "NaN"}]}}, "invalid_response"),
])
async def test_retrieval_fault_is_not_silent_empty(monkeypatch, kwargs, expected):
    knowledge_transport(monkeypatch, **kwargs)
    result = await RAGService().retrieve("nginx")
    assert result["retrieval_status"] == expected
    assert result["degraded"] is True
    assert result["degradation_reason"]
    assert result["results"] == []
    assert result["trust_score"] == 0.0


@pytest.mark.asyncio
@pytest.mark.parametrize("results,expected", [([], "empty"), ([{"content": "check nginx", "source": "ops.md"}], "ok")])
async def test_valid_retrieval_preserves_evidence(monkeypatch, results, expected):
    citation = {"citation_id": 1, "source": "ops.md", "score": 0.8}
    knowledge_transport(monkeypatch, payload={"results": results, "citations": [citation], "evidences": [{"content": "check nginx"}], "trust_score": 0.8})
    result = await RAGService().retrieve("nginx")
    assert result["retrieval_status"] == expected
    assert result["degraded"] is False
    assert result["citations"] == [citation]
    assert result["results"] == results


@pytest.mark.asyncio
async def test_model_recovers_without_stale_degradation(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    service = LLMService()

    async def unavailable(**kwargs):
        raise ConnectionError("test offline")

    async def recovered(**kwargs):
        return "real answer"

    monkeypatch.setattr(service, "_ollama_generate", unavailable)
    await service.generate("first")
    assert service.degraded is True
    monkeypatch.setattr(service, "_ollama_generate", recovered)
    assert await service.generate("second") == "real answer"
    assert (service.degraded, service.degradation_reason, service.effective_provider) == (False, "", "ollama")


@pytest.mark.asyncio
async def test_partial_real_stream_is_never_mixed_with_mock(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    service = LLMService()

    async def interrupted(**kwargs):
        yield "real partial"
        raise ConnectionError("test interrupted")

    monkeypatch.setattr(service, "_ollama_stream", interrupted)
    output = []
    with pytest.raises(LLMException):
        async for chunk in service.generate_stream("question"):
            output.append(chunk)
    assert output == ["real partial"]
    assert service.degraded is True
    assert service.effective_provider == "ollama"


@pytest.mark.asyncio
async def test_stream_recovers_after_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    service = LLMService()

    async def unavailable(**kwargs):
        raise ConnectionError("test offline")
        yield  # async generator, failure before first token

    async def recovered(**kwargs):
        yield "real answer"

    monkeypatch.setattr(service, "_ollama_stream", unavailable)
    assert "模拟回答" in "".join([chunk async for chunk in service.generate_stream("first")])
    assert service.degraded is True
    monkeypatch.setattr(service, "_ollama_stream", recovered)
    assert [chunk async for chunk in service.generate_stream("second")] == ["real answer"]
    assert (service.degraded, service.degradation_reason, service.effective_provider) == (False, "", "ollama")


@pytest.mark.asyncio
@pytest.mark.parametrize("lines", [[], [{"done": True}], [{"response": "partial"}], [{"error": "model missing"}], [{"response": "first", "done": "false"}, {"response": "tail", "done": True}]])
async def test_incomplete_ollama_protocol_raises(monkeypatch, lines):
    real_client = httpx.AsyncClient
    body = "\n".join(json.dumps(line) for line in lines)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(**kwargs, transport=httpx.MockTransport(lambda request: httpx.Response(200, text=body))))
    with pytest.raises(LLMException):
        _ = [chunk async for chunk in LLMService()._ollama_stream("question", None)]


@pytest.mark.asyncio
async def test_chat_reports_retrieval_degradation_in_both_modes(monkeypatch):
    knowledge_transport(monkeypatch, status=503)
    service = ChatService()
    request = ChatRequest(message="nginx")
    response = await service.chat(request)
    assert response.metadata["rag_status"] == "unavailable"
    assert response.metadata["rag_degraded"] is True
    events = [event async for event in service.chat_stream(request)]
    done = next(event["data"] for event in events if event["event"] == "done")
    assert done["metadata"]["rag_status"] == "unavailable"


@pytest.mark.asyncio
async def test_chat_stream_interruption_has_error_and_no_done(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    service = ChatService()

    async def interrupted(**kwargs):
        yield "real partial"
        raise ConnectionError("test interrupted")

    monkeypatch.setattr(service.llm, "_ollama_stream", interrupted)
    events = [event async for event in service.chat_stream(ChatRequest(message="nginx", use_rag=False))]
    assert [event["data"]["delta"] for event in events if event["event"] == "token"] == ["real partial"]
    assert events[-1]["event"] == "error"
    assert events[-1]["data"]["code"] == "LLM_STREAM_INTERRUPTED"
    assert not any(event["event"] == "done" for event in events)


def test_chat_inspector_preserves_explicit_verification_requirement(client):
    response = client.post("/api/chat", json={
        "message": "核验任务",
        "use_rag": False,
        "metadata": {
            "agent_claim": "处理就这样了",
            "verification_required": True,
            "evidence": [{"content": "处理就这样了", "source": "test"}],
        },
    })
    assert response.status_code == 200
    inspection = response.json()["metadata"]["inspection"]
    assert inspection["verification_result"]["required"] is True
    assert inspection["verification_result"]["status"] == "unverified"
    assert inspection["status"] == "WARN"


def test_chat_inspector_explicit_request_alone_is_not_skipped(client):
    response = client.post("/api/chat", json={"message": "检查任务", "use_rag": False, "metadata": {"verification_required": True}})
    assert response.status_code == 200
    inspection = response.json()["metadata"]["inspection"]
    assert inspection["status"] == "WARN"
    assert inspection["requires_human"] is True


@pytest.mark.asyncio
async def test_progress_only_reports_executed_stages():
    events = [event async for event in ChatService().chat_stream(ChatRequest(message="nginx", use_rag=False, images=["screen.png"]))]
    stages = [event["data"]["stage"] for event in events if event["event"] == "thinking"]
    assert stages == ["attachments", "answer"]
    done = next(event["data"] for event in events if event["event"] == "done")
    assert done["metadata"]["rag_status"] == "disabled"


def test_http_sse_route_exposes_interruption_without_done(client, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    async def interrupted(self, **kwargs):
        yield "real partial"
        raise ConnectionError("test interrupted")

    monkeypatch.setattr(LLMService, "_ollama_stream", interrupted)
    response = client.post("/api/chat/stream", json={"message": "nginx", "use_rag": False})
    assert response.status_code == 200  # SSE headers precede provider execution.
    assert '"delta": "real partial"' in response.text
    assert "event: error\n" in response.text
    assert "LLM_STREAM_INTERRUPTED" in response.text
    assert "event: done\n" not in response.text
