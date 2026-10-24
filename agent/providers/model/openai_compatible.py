"""
SmartOps OpenAI-Compatible Model Provider.

用于接入支持 OpenAI-compatible Chat Completions API
的外部大模型。

统一配置：

    base_url
    api_key
    model

特点：

    - 用户可以自行配置 API Key
    - 支持不同模型
    - 支持不同 Base URL
    - 不把 API Key 写入日志
    - 支持 timeout
    - 返回统一 ModelResponse

本 Provider 不负责：

    Permission
    Risk
    Approval
    Sandbox

这些仍由上层 SmartOps Harness 负责。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

from agent.sdk.model import ModelProvider, ModelResponse


@dataclass(slots=True)
class OpenAICompatibleConfig:
    """
    OpenAI-Compatible Provider 配置。
    """

    base_url: str

    api_key: str

    model: str

    timeout: float = 60.0

    temperature: float = 0.2

    extra_headers: dict[str, str] = field(
        default_factory=dict
    )


class OpenAICompatibleModelProvider(
    ModelProvider
):
    """
    OpenAI-Compatible Model Provider。
    """

    def __init__(
        self,
        config: OpenAICompatibleConfig,
    ) -> None:

        self.config = config

        self.base_url = (
            config.base_url.rstrip("/")
        )

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float | None = None,
        **kwargs: Any,
    ) -> ModelResponse:

        if not prompt.strip():
            raise ValueError(
                "prompt 不能为空"
            )

        messages: list[
            dict[str, str]
        ] = []

        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt,
                }
            )

        messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": (
                self.config.temperature
                if temperature is None
                else temperature
            ),
        }

        payload.update(
            kwargs
        )

        headers = {
            "Authorization": (
                f"Bearer {self.config.api_key}"
            ),
            "Content-Type": (
                "application/json"
            ),
        }

        headers.update(
            self.config.extra_headers
        )

        url = (
            f"{self.base_url}"
            "/chat/completions"
        )

        async with httpx.AsyncClient(
            timeout=self.config.timeout
        ) as client:

            response = await client.post(
                url,
                headers=headers,
                json=payload,
            )

            response.raise_for_status()

            data = response.json()

        content = (
            data
            .get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )

        usage = (
            data.get(
                "usage",
                {}
            )
        )

        return ModelResponse(
            content=str(content),
            model=str(
                data.get(
                    "model",
                    self.config.model,
                )
            ),
            usage=usage,
            raw=data,
        )


__all__ = [
    "OpenAICompatibleConfig",
    "OpenAICompatibleModelProvider",
]