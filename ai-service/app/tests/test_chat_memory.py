"""对话记忆闭环：记忆注入、回写规则与降级行为。"""

import pytest

from app.schemas.chat import ChatRequest
from app.services.chat import ChatService
from app.services.memory import MemoryService


class FakeMemory(MemoryService):
    """复用真实的渲染/抽取规则，只替换网络读写。"""

    def __init__(self, recalled=None):
        super().__init__(base_url="", token="", enabled=False)
        self.recalled = recalled or []
        self.recalled_user = None
        self.written = []

    async def recall(self, user_id, query, limit=None):
        self.recalled_user = user_id
        return self.recalled

    async def remember(self, user_id, incident_key, preferred_action, source_refs):
        self.written.append((user_id, incident_key, preferred_action, source_refs))
        return {"id": 1}


class FakeLLM:
    degraded = False
    effective_provider = "mock"
    degradation_reason = ""
    last_llm_perf = {"provider": "fake"}

    def __init__(self):
        self.prompts = []

    async def generate(self, prompt, *, system_prompt=None, model=None, **kwargs):
        self.prompts.append(prompt)
        return "收到。"

    async def generate_stream(self, prompt, *, system_prompt=None, model=None, **kwargs):
        self.prompts.append(prompt)
        yield "收到。"


MEMORY_ITEM = {
    "incidentKey": "nginx:502",
    "preferredAction": "先看网关日志",
    "confidence": 0.8,
    "evidenceCount": 3,
}


def test_extract_preference_only_takes_explicit_rules():
    rule = MemoryService.extract_preference("以后遇到 nginx 502，先看网关日志")
    assert rule["incident_key"] == "nginx 502"
    assert rule["preferred_action"] == "看网关日志"

    generic = MemoryService.extract_preference("以后都用中文回答我")
    assert generic["incident_key"] == "通用约定"
    assert "中文" in generic["preferred_action"]

    # 普通问答、疑问句、太短的话都不算规则，不能写进记忆。
    assert MemoryService.extract_preference("nginx 502 怎么排查？") is None
    assert MemoryService.extract_preference("以后遇到这个先看日志吗？") is None
    assert MemoryService.extract_preference("在吗") is None


def test_extract_preference_source_refs_is_stable():
    first = MemoryService.extract_preference("以后遇到磁盘满，先看 inode")
    second = MemoryService.extract_preference("以后遇到磁盘满，先看 inode")
    assert first["source_refs"] == second["source_refs"]
    assert first["source_refs"].startswith("chat-pref:")


def test_render_section_is_empty_without_memories():
    assert MemoryService.render_section([]) == ""
    section = MemoryService.render_section([MEMORY_ITEM])
    assert "历史记忆" in section
    assert "nginx:502" in section and "先看网关日志" in section
    assert "0.80" in section


@pytest.mark.asyncio
async def test_memory_is_not_configured_without_internal_token():
    service = MemoryService(base_url="http://127.0.0.1:9", token="", enabled=True)
    assert service.configured is False
    assert await service.recall("1", "nginx 502") == []
    assert await service.remember("1", "k", "a", "s") is None


@pytest.mark.asyncio
async def test_chat_injects_recalled_memory_into_prompt():
    llm = FakeLLM()
    memory = FakeMemory(recalled=[MEMORY_ITEM])
    service = ChatService(llm_service=llm, memory_service=memory)

    response = await service.chat(
        ChatRequest(message="nginx 502 又出现了", use_rag=False),
        user_id="7",
    )

    assert memory.recalled_user == "7"
    assert "历史记忆" in llm.prompts[0]
    assert "先看网关日志" in llm.prompts[0]
    # 记忆段必须落在用户问题之前，保持 prompt 的稳定前缀结构
    assert llm.prompts[0].index("历史记忆") < llm.prompts[0].index("<user_input>")
    assert response.metadata["memory"]["recalled"] == 1


@pytest.mark.asyncio
async def test_chat_writes_back_explicit_preference():
    memory = FakeMemory()
    service = ChatService(llm_service=FakeLLM(), memory_service=memory)

    response = await service.chat(
        ChatRequest(message="以后遇到 nginx 502，先看网关日志", use_rag=False),
        user_id="7",
    )

    assert response.metadata["memory"]["learned"] is True
    user_id, incident_key, preferred_action, source_refs = memory.written[0]
    assert user_id == "7"
    assert incident_key == "nginx 502"
    assert "网关日志" in preferred_action
    assert source_refs.startswith("chat-pref:")


@pytest.mark.asyncio
async def test_chat_does_not_write_memory_without_authenticated_user():
    memory = FakeMemory()
    service = ChatService(llm_service=FakeLLM(), memory_service=memory)

    response = await service.chat(
        ChatRequest(message="以后遇到 nginx 502，先看网关日志", use_rag=False)
    )

    assert memory.written == []
    assert response.metadata["memory"] == {"recalled": 0, "learned": False}


@pytest.mark.asyncio
async def test_stream_chat_uses_the_same_memory_loop():
    memory = FakeMemory(recalled=[MEMORY_ITEM])
    service = ChatService(llm_service=FakeLLM(), memory_service=memory)

    events = [
        event
        async for event in service.chat_stream(
            ChatRequest(message="以后遇到 nginx 502，先看网关日志", use_rag=False),
            user_id="7",
        )
    ]

    done = next(event for event in events if event["event"] == "done")
    assert done["data"]["metadata"]["memory"] == {"recalled": 1, "learned": True}
    assert memory.written[0][1] == "nginx 502"
