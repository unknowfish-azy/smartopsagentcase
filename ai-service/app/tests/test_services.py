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


@pytest.mark.asyncio
async def test_openai_compatible_generate_uses_chat_completions(monkeypatch):
    """DashScope 百炼/微调模型走 OpenAI 兼容端点，system 与 model 原样透传。"""

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [{"message": {"content": "来自微调模型的回答"}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 5},
            }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, json, headers):
            assert url.endswith("/compatible-mode/v1/chat/completions")
            assert headers["Authorization"] == "Bearer sk-test"
            assert json["model"] == "qwen2.5-7b-ops-sft"
            assert json["stream"] is False
            assert json["messages"] == [
                {"role": "system", "content": "系统提示"},
                {"role": "user", "content": "真实模型问题"},
            ]
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_model", "qwen2.5-7b-ops-sft")
    monkeypatch.setattr(
        settings, "llm_base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")

    service = LLMService()
    result = await service.generate("真实模型问题", system_prompt="系统提示")

    assert result == "来自微调模型的回答"
    assert service.degraded is False
    assert service.effective_provider == "openai-compatible"
    assert service.last_llm_perf["prompt_eval_count"] == 12


@pytest.mark.asyncio
async def test_openai_compatible_stream_reads_sse(monkeypatch):
    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def aiter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"真"}}]}'
            yield 'data: {"choices":[{"delta":{"content":"回答"}}]}'
            yield "data: [DONE]"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            assert kwargs["trust_env"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        def stream(self, method, url, json, headers):
            assert method == "POST"
            assert url.endswith("/chat/completions")
            assert json["stream"] is True
            assert headers["Authorization"] == "Bearer sk-test"
            return FakeResponse()

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_base_url", "http://localhost:9000/v1")
    monkeypatch.setattr(settings, "llm_api_key", "sk-test")

    service = LLMService()
    chunks = []
    async for chunk in service.generate_stream("流式问题"):
        chunks.append(chunk)

    assert service.degraded is False, service.degradation_reason
    assert chunks == ["真", "回答"]


@pytest.mark.asyncio
async def test_openai_compatible_missing_api_key_marks_degraded(monkeypatch):
    """未配置密钥时不伪造真实回答：如实标记降级并回落到 mock。"""

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, *args, **kwargs):
            raise AssertionError("缺少密钥时不应发起真实请求")

    monkeypatch.setattr("httpx.AsyncClient", FakeClient)
    monkeypatch.setattr(settings, "llm_provider", "openai-compatible")
    monkeypatch.setattr(settings, "llm_api_key", "")

    service = LLMService()
    result = await service.generate("没有密钥的问题")

    assert "没有密钥的问题" in result
    assert service.degraded is True
    assert service.effective_provider == "mock"
    assert "LLM_API_KEY" in service.degradation_reason


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
