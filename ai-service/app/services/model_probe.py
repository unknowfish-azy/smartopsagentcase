"""模型可用性探测（W7 事件驱动的前置闸门）。

系统触发没有用户会话，也没有人在旁边判断"模型是不是挂了"。因此触发前必须
真实探测一次：不可用就只记 WARN、不生成任何初诊事件，绝不输出"看起来像结论"
的占位内容。

探测只看**可达性**，不做生成质量评估：
* ``mock``：没有真实模型，直接判不可用；
* ``ollama``：``GET {llm_base_url}/api/tags``；
* ``openai-compatible``：``GET {llm_base_url}/models``（有 key 时带上）。
"""

from __future__ import annotations

import logging

import httpx

from ..core.config import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SEC = 2.0


async def probe_llm_availability(
    *,
    timeout: float = DEFAULT_TIMEOUT_SEC,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[bool, str]:
    """返回 ``(available, reason)``；不可用时 reason 说明真实原因。"""
    provider = str(getattr(settings, "llm_provider", "") or "").strip().lower()
    if provider == "mock":
        return False, "LLM_PROVIDER_MOCK"
    if provider == "ollama":
        url = _join(settings.llm_base_url, "/api/tags")
        headers: dict[str, str] = {}
    elif provider == "openai-compatible":
        url = _join(settings.llm_base_url, "/models")
        api_key = str(getattr(settings, "llm_api_key", "") or "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    else:
        return False, f"LLM_PROVIDER_UNSUPPORTED:{provider or 'empty'}"

    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
            response = await client.get(url, headers=headers)
    except Exception as failure:  # noqa: BLE001 - 探测失败一律视为不可用
        logger.warning("model_probe.failed provider=%s reason=%s", provider, failure)
        return False, f"LLM_PROBE_FAILED:{type(failure).__name__}"
    if response.status_code == 200:
        return True, ""
    return False, f"LLM_PROBE_HTTP_{response.status_code}"


def _join(base_url: str, path: str) -> str:
    return (base_url or "").rstrip("/") + path
