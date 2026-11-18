"""从环境变量创建 ModelProvider（P2 阶段 0：大模型密钥接入）。

Provider 实现早已就绪（openai-compatible / mock / fallback 降级链），本模块只负责
「按 env 配置把 Provider 建出来」，复用项目既有环境变量约定：

    LLM_PROVIDER   mock（默认，零依赖安全兜底）/ ollama / openai-compatible
    LLM_MODEL      模型名，openai-compatible 时填大模型（如 kimi-k2、deepseek-chat、qwen-plus）
    LLM_BASE_URL   openai-compatible 必填，需含 OpenAI 兼容路径（通常以 /v1 结尾）
    LLM_API_KEY    openai-compatible 必填（大模型密钥）；ollama 可留空（自动用占位）
    LLM_TIMEOUT    可选，默认 60s
    LLM_TEMPERATURE 可选，默认 0.2（研判类任务低温更稳）

安全约束：
* 默认 mock——未配置密钥时绝不向任何外部端点发请求；
* 密钥只从 env 读，不写日志、不进异常信息；
* openai-compatible 缺 base_url/model 时直接 ValueError（配置错误要尽早暴露，
  而不是运行时才"静默回到 mock"让人误以为接上了大模型）。
"""

from __future__ import annotations

import logging
import os

from agent.sdk.model import ModelProvider

from .fallback import FallbackModelProvider
from .mock import MockModelProvider
from .openai_compatible import OpenAICompatibleConfig, OpenAICompatibleModelProvider

logger = logging.getLogger(__name__)

# Ollama 的 OpenAI 兼容端点固定挂在 /v1 下
_OLLAMA_DEFAULT_BASE_URL = "http://localhost:11434/v1"


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        logger.warning("env %s=%r 非法，回退默认 %s", name, raw, default)
        return default


def _build_openai_compatible(*, ollama: bool = False) -> OpenAICompatibleModelProvider:
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    model = os.getenv("LLM_MODEL", "").strip()
    api_key = os.getenv("LLM_API_KEY", "").strip()

    if ollama:
        # Ollama 本地服务：base_url 缺省补 /v1，api_key 不校验用占位
        base_url = base_url or _OLLAMA_DEFAULT_BASE_URL
        if not base_url.rstrip("/").endswith("/v1"):
            base_url = base_url.rstrip("/") + "/v1"
        api_key = api_key or "ollama"
        model = model or "qwen3:1.7b"
    else:
        if not base_url:
            raise ValueError("openai-compatible 需要配置 LLM_BASE_URL（含 /v1 的 OpenAI 兼容地址）")
        if not model or model == "mock-model":
            raise ValueError("openai-compatible 需要配置 LLM_MODEL 为目标大模型（当前是占位 mock-model）")

    config = OpenAICompatibleConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout=_float_env("LLM_TIMEOUT", 60.0),
        temperature=_float_env("LLM_TEMPERATURE", 0.2),
    )
    # 不打印 api_key；只记录脱敏后的接入信息
    logger.info(
        "model.provider built type=%s base_url=%s model=%s key=%s",
        "ollama" if ollama else "openai-compatible",
        config.base_url,
        config.model,
        "set" if api_key and api_key != "ollama" else "placeholder",
    )
    return OpenAICompatibleModelProvider(config)


def build_model_provider_from_env() -> ModelProvider:
    """按 LLM_PROVIDER 创建对应 Provider；未配置/未知值安全回退 mock。

    可选降级链：设置 LLM_FALLBACK_PROVIDER=mock 时，主模型外包一层
    FallbackModelProvider，主模型故障自动切到 mock，保证链路永远有产出。
    """
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()

    if provider == "openai-compatible":
        primary: ModelProvider = _build_openai_compatible()
    elif provider == "ollama":
        primary = _build_openai_compatible(ollama=True)
    elif provider == "mock":
        primary = MockModelProvider(os.getenv("LLM_MODEL", "mock-model"))
    else:
        logger.warning("未知 LLM_PROVIDER=%r，回退 mock", provider)
        primary = MockModelProvider("mock-model")

    fallback_kind = os.getenv("LLM_FALLBACK_PROVIDER", "").strip().lower()
    if fallback_kind == "mock" and not isinstance(primary, MockModelProvider):
        return FallbackModelProvider(
            [primary, MockModelProvider("mock-model")], name="primary->mock"
        )
    return primary


__all__ = ["build_model_provider_from_env"]
