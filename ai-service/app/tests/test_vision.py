"""多模态视觉链路契约（2026-11-16）。

诚实性铁律：带图请求绝不静默降级到 mock（mock 无法看图）。
- 正常：把 data URL 剥成裸 base64 放进 Ollama payload.images，流式吐字。
- 失败：Ollama 明确"模型不支持多模态"时抛 LLMException，不伪造识别。
- mock provider：直接拒绝并说明需要视觉模型。
"""
import json

import pytest

from app.core.config import settings
from app.core.exceptions import LLMException
from app.services.llm import LLMService


PNG_DATA_URL = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"


class _FakeResponse:
    def __init__(self, status_code=200, lines=None):
        self.status_code = status_code
        self._lines = lines or []

    async def aread(self):
        return b'{"error":"Multimodal data provided, but model does not support multimodal requests."}'

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeStreamCtx:
    def __init__(self, response):
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *args):
        return False


class _FakeClient:
    def __init__(self, response):
        self.response = response
        self.sent_payload = None

    def stream(self, method, url, json=None):
        self.sent_payload = json
        return _FakeStreamCtx(self.response)


class _FakePool:
    def __init__(self, client):
        self.client = client

    def acquire(self):
        return _FakeAcquire(self.client)


class _FakeAcquire:
    def __init__(self, client):
        self.client = client

    async def __aenter__(self):
        return self.client

    async def __aexit__(self, *args):
        return False


@pytest.mark.asyncio
async def test_vision_stream_sends_base64_and_yields_tokens(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_vision_model", "qwen2.5vl:3b")
    lines = [
        json.dumps({"response": "这是", "done": False}),
        json.dumps({"response": "一张图", "done": True, "prompt_eval_count": 10, "eval_count": 5}),
    ]
    client = _FakeClient(_FakeResponse(200, lines))
    monkeypatch.setattr("app.services.llm.http_pool", _FakePool(client))

    svc = LLMService()
    chunks = [chunk async for chunk in svc.generate_vision_stream("描述图片", images=[PNG_DATA_URL])]

    assert "".join(chunks) == "这是一张图"
    assert client.sent_payload["model"] == "qwen2.5vl:3b"
    assert client.sent_payload["images"] == ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"]
    assert svc.last_llm_perf.get("multimodal") is True
    assert svc.last_llm_perf.get("image_count") == 1


@pytest.mark.asyncio
async def test_vision_stream_rejects_when_model_lacks_multimodal(monkeypatch):
    """模型不支持多模态 → 明确报错，绝不伪造"已看图"。"""
    monkeypatch.setattr(settings, "llm_provider", "ollama")
    monkeypatch.setattr(settings, "llm_vision_model", "qwen3:1.7b")
    client = _FakeClient(_FakeResponse(400, []))
    monkeypatch.setattr("app.services.llm.http_pool", _FakePool(client))

    svc = LLMService()
    with pytest.raises(LLMException) as exc:
        async for _ in svc.generate_vision_stream("描述图片", images=[PNG_DATA_URL]):
            pass
    assert "多模态" in str(exc.value) or "失败" in str(exc.value)


@pytest.mark.asyncio
async def test_vision_stream_rejects_mock_provider(monkeypatch):
    """mock provider 无法看图 → 直接拒绝，不静默降级成文本 mock。"""
    monkeypatch.setattr(settings, "llm_provider", "mock")
    svc = LLMService()
    with pytest.raises(LLMException) as exc:
        async for _ in svc.generate_vision_stream("描述图片", images=[PNG_DATA_URL]):
            pass
    assert "不支持图像" in str(exc.value)


def test_normalize_images_filters_non_images():
    out = LLMService._normalize_images([
        PNG_DATA_URL,
        "data:text/plain;base64,SGVsbG8=",  # 非图片 data URL 应丢弃
        "   ",
        "iVBORw0KGgo=",  # 裸 base64 保留
    ])
    assert out == ["iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ", "iVBORw0KGgo="]
