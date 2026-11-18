"""阶段 0：大模型 Provider 工厂 + ReAct 组合根测试。"""

import asyncio

import pytest

from agent.executor.models import ExecutionContext
from agent.providers.model.factory import build_model_provider_from_env
from agent.providers.model.mock import MockModelProvider
from agent.providers.model.fallback import FallbackModelProvider
from agent.providers.model.openai_compatible import OpenAICompatibleModelProvider
from agent.planner.react_agent import build_react_planner


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    for key in ("LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY",
                "LLM_TIMEOUT", "LLM_TEMPERATURE", "LLM_MAX_TOKENS", "LLM_FALLBACK_PROVIDER",
                "SMARTOPS_MODEL_LOCAL_BASE_URL"):
        monkeypatch.delenv(key, raising=False)


# ---------------------------------------------------------------------------
# build_model_provider_from_env
# ---------------------------------------------------------------------------


def test_default_is_mock_without_env():
    provider = build_model_provider_from_env()
    assert isinstance(provider, MockModelProvider)


def test_explicit_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("LLM_MODEL", "mock-model")
    assert isinstance(build_model_provider_from_env(), MockModelProvider)


def test_openai_compatible_with_full_config(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.moonshot.cn/v1")
    monkeypatch.setenv("LLM_MODEL", "kimi-k2")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-secret")

    provider = build_model_provider_from_env()

    assert isinstance(provider, OpenAICompatibleModelProvider)
    assert provider.config.base_url == "https://api.moonshot.cn/v1"
    assert provider.config.model == "kimi-k2"
    assert provider.config.api_key == "sk-test-secret"


def test_openai_compatible_missing_base_url_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_MODEL", "kimi-k2")
    with pytest.raises(ValueError, match="LLM_BASE_URL"):
        build_model_provider_from_env()


def test_openai_compatible_placeholder_model_raises(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.moonshot.cn/v1")
    monkeypatch.setenv("LLM_MODEL", "mock-model")  # 占位未改
    with pytest.raises(ValueError, match="LLM_MODEL"):
        build_model_provider_from_env()


def test_ollama_auto_appends_v1_and_placeholder_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:11434")
    monkeypatch.setenv("LLM_MODEL", "qwen3:1.7b")

    provider = build_model_provider_from_env()

    assert isinstance(provider, OpenAICompatibleModelProvider)
    assert provider.config.base_url == "http://localhost:11434/v1"
    assert provider.config.api_key == "ollama"  # 占位，非真实密钥
    assert provider.config.model == "qwen3:1.7b"


def test_unknown_provider_falls_back_to_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "some-weird-provider")
    assert isinstance(build_model_provider_from_env(), MockModelProvider)


def test_fallback_chain_wraps_primary(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    monkeypatch.setenv("LLM_MODEL", "deepseek-chat")
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_FALLBACK_PROVIDER", "mock")

    provider = build_model_provider_from_env()

    assert isinstance(provider, FallbackModelProvider)
    assert len(provider.chain) == 2  # 主模型 + mock 兜底


def test_timeout_and_temperature_from_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setenv("LLM_MODEL", "gpt-4o")
    monkeypatch.setenv("LLM_API_KEY", "sk-x")
    monkeypatch.setenv("LLM_TIMEOUT", "120")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.1")
    monkeypatch.setenv("LLM_MAX_TOKENS", "1536")

    provider = build_model_provider_from_env()
    assert provider.config.timeout == 120.0
    assert provider.config.temperature == 0.1
    assert provider.config.max_tokens == 1536


# ---------------------------------------------------------------------------
# build_react_planner 组合根
# ---------------------------------------------------------------------------


def test_build_react_planner_default_wires_perception_tools():
    planner = build_react_planner()  # 默认 mock provider + 感知工具
    names = {t.name for t in planner.tool_registry.list_tools()}
    assert {"nn.anomaly", "nn.rootcause", "nn.log_classify", "nn.retrieve"} <= names
    assert isinstance(planner.model_provider, MockModelProvider)


def test_build_react_planner_runs_with_fake_provider_and_http():
    from agent.sdk.model import ModelProvider, ModelResponse

    class FinalProvider(ModelProvider):
        @property
        def name(self):
            return "fake"

        async def generate(self, prompt, **kwargs):
            return ModelResponse(content="Final Answer: 已接入大模型，根因研判完成。",
                                 model="fake", provider="fake", metadata={})

    async def fake_http(url, payload):
        return {"ok": True, "results": []}

    planner = build_react_planner(provider=FinalProvider(), perception_http_post=fake_http)
    result = planner.run("目标", ExecutionContext("r", "u"))

    assert result.status == "completed"
    assert "根因研判完成" in result.final_answer
    assert planner.model_provider.name == "fake"
