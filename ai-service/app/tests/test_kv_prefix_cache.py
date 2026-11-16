# -*- coding: utf-8 -*-
"""KV-CACHE：prompt 前缀复用优化的行为测试。

覆盖三件事：
1. _build_prompt 稳定前缀在前、易变内容在后（同 context 不同问题的前缀逐字节一致）；
2. Ollama payload 携带 keep_alive（模型与 KV 缓存驻留的前提）；
3. chat 响应 metadata 暴露 llm_perf（mock 下结构一致，如实标注 provider）。
"""

import pytest


def test_build_prompt_keeps_stable_prefix_across_messages():
    from app.services.chat import ChatService

    context = "证据一：nginx 502 多为 upstream 超时。\n证据二：可查 error_log 的 upstream 行。"

    prompt_a = ChatService._build_prompt(message="502 怎么排查", context=context)
    prompt_b = ChatService._build_prompt(message="5xx 的一般思路是什么", context=context)

    # 用户问题在末尾：两份 prompt 的公共前缀必须覆盖到知识库证据段末尾
    prefix_len = 0
    for ca, cb in zip(prompt_a, prompt_b):
        if ca != cb:
            break
        prefix_len += 1
    assert "知识库证据：" in prompt_a[:prefix_len]
    assert prompt_a[:prefix_len] == prompt_b[:prefix_len]

    # 易变内容只在末尾：message 出现在公共前缀之后
    assert prompt_a.endswith("502 怎么排查\n")
    assert prompt_b.endswith("5xx 的一般思路是什么\n")
    # 语义要素齐全且顺序为 要求 → 证据 → 问题
    assert prompt_a.index("要求：") < prompt_a.index("知识库证据：") < prompt_a.index("用户问题：")


def test_build_prompt_images_section_between_context_and_message():
    from app.services.chat import ChatService

    prompt = ChatService._build_prompt(
        message="看下这张截图",
        context="证据内容",
        images=["cpu.png"],
    )
    assert prompt.index("知识库证据：") < prompt.index("图像证据（") < prompt.index("用户问题：")
    assert "- cpu.png" in prompt


def test_payload_includes_keep_alive():
    from app.services.llm import LLMService
    from app.core.config import settings

    payload = LLMService._payload("问题", "系统提示", stream=True, model=None)
    # KV-CACHE：keep_alive 以 Go duration 时长串传递（默认 1800s）
    assert payload["keep_alive"] == f"{settings.llm_keep_alive_sec}s"
    assert payload["keep_alive"].endswith("s")
    assert payload["stream"] is True


def test_payload_num_ctx_only_when_configured(monkeypatch):
    from app.services.llm import LLMService
    from app.core.config import settings

    # 0 = 不传 options，沿用 Ollama 服务端默认
    monkeypatch.setattr(settings, "llm_num_ctx", 0)
    payload = LLMService._payload("问题", None, stream=False, model=None)
    assert "options" not in payload

    # 配置后显式传入 options.num_ctx
    monkeypatch.setattr(settings, "llm_num_ctx", 8192)
    payload = LLMService._payload("问题", None, stream=False, model=None)
    assert payload["options"] == {"num_ctx": 8192}


@pytest.mark.asyncio
async def test_chat_metadata_exposes_llm_perf(monkeypatch):
    from app.core.config import settings
    from app.services.chat import ChatService
    from app.schemas.chat import ChatRequest

    monkeypatch.setattr(settings, "llm_provider", "mock")
    monkeypatch.setattr(settings, "llm_model", "mock-model")

    class FakeRAG:
        async def retrieve(self, **kwargs):
            return {
                "results": [],
                "citations": [],
                "evidences": [],
                "trust_score": 0.0,
                "retrieval_status": "empty",
                "degraded": False,
            }

        def build_context(self, results):
            return ""

    from app.services import chat as chat_module
    chat_module._shared_rag_cache = None
    service = ChatService(rag_service=FakeRAG())

    request = ChatRequest(
        message="Redis 打满了怎么排查",
        use_rag=False,
        metadata={},
    )
    response = await service.chat(request)

    # mock provider 也如实标注，结构一致（真实 ollama 时为计数/耗时字段）
    assert response.metadata["llm_perf"]["provider"] == "mock"
