import pytest

from app.services.llm import LLMService
from app.services.rag import RAGService
from app.core.config import settings


@pytest.mark.asyncio
async def test_mock_llm():

    service = LLMService()

    result = await service.generate(
        "测试问题"
    )

    assert isinstance(
        result,
        str,
    )

    assert "测试问题" in result


@pytest.mark.asyncio
async def test_ollama_llm_calls_real_generate_endpoint(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"response": "来自 Ollama 的回答"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json):
            assert url.endswith("/api/generate")
            assert json["model"] == "qwen2.5:1.7b"
            assert json["stream"] is False
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_model", "qwen2.5:1.7b")

    service = LLMService()
    result = await service.generate("真实模型问题")

    assert result == "来自 Ollama 的回答"
    assert service.degraded is False
    assert service.effective_provider == "ollama"


@pytest.mark.asyncio
async def test_ollama_connection_failure_falls_back_and_marks_degraded(monkeypatch):
    class FailingClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            raise RuntimeError("ollama unavailable")

    monkeypatch.setattr("httpx.AsyncClient", FailingClient)
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_model", "qwen2.5:1.7b")

    service = LLMService()
    result = await service.generate("降级问题")

    assert "降级问题" in result
    assert service.degraded is True
    assert service.effective_provider == "mock"
    assert service.degradation_reason


@pytest.mark.asyncio
async def test_ollama_stream_reads_ndjson(monkeypatch):
    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            yield '{"response":"真"}'
            yield '{"response":"回答","done":true}'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, json):
            assert method == "POST"
            assert url.endswith("/api/generate")
            assert json["stream"] is True
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "ollama")

    service = LLMService()
    chunks = []
    async for chunk in service.generate_stream("流式问题"):
        chunks.append(chunk)

    assert service.degraded is False, service.degradation_reason
    assert chunks == ["真", "回答"]


def test_rag_context():

    context = RAGService.build_context(
        [
            {
                "content": "systemctl restart nginx",
                "source": "nginx.md",
                "version": "ubuntu-22.04",
            }
        ]
    )

    assert "nginx" in context

    assert "ubuntu-22.04" in context


def test_empty_rag_context():

    context = RAGService.build_context(
        []
    )

    assert "没有检索到" in context
