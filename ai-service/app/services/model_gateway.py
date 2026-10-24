"""
SmartOps Model Gateway.

职责：

    connection_id
        ↓
    Backend
        ↓
    获取模型运行配置
        ↓
    OpenAI-Compatible Provider
        ↓
    Model Response

API Key 只在服务端运行时短暂存在。

禁止：

    API Key → frontend
    API Key → audit log
    API Key → normal application log
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ModelGatewayError(RuntimeError):
    """模型网关异常。"""


@dataclass(slots=True)
class RuntimeModelConfig:
    """
    Runtime 模型配置。
    """

    connection_id: int

    provider: str

    base_url: str

    model: str

    timeout: float = 60.0


class ModelGateway:
    """
    多模型统一调用网关。
    """

    def __init__(
        self,
        *,
        backend_url: str,
        internal_token: str,
        timeout: float = 10.0,
    ) -> None:
        self.backend_url = (
            backend_url.rstrip("/")
        )

        self.internal_token = (
            internal_token
        )

        self.timeout = timeout

    async def get_runtime_config(
        self,
        connection_id: int,
        user_id: int,
    ) -> RuntimeModelConfig:

        url = (
            f"{self.backend_url}"
            f"/api/model-connections/"
            f"{connection_id}/runtime"
        )

        headers = {
            "X-User-Id": str(user_id),
            "X-SmartOps-Internal-Token": (
                self.internal_token
            ),
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout
            ) as client:

                response = await client.get(
                    url,
                    headers=headers,
                )

                response.raise_for_status()

                data: dict[str, Any] = (
                    response.json()
                )

        except httpx.HTTPError as exc:
            raise ModelGatewayError(
                f"获取模型配置失败：{exc}"
            ) from exc

        return RuntimeModelConfig(
            connection_id=connection_id,
            provider=str(
                data.get(
                    "provider",
                    "",
                )
            ),
            base_url=str(
                data.get(
                    "baseUrl",
                    "",
                )
            ),
            model=str(
                data.get(
                    "modelName",
                    "",
                )
            ),
            timeout=float(
                data.get(
                    "timeoutSeconds",
                    60,
                )
            ),
        )

    async def chat(
        self,
        *,
        connection_id: int,
        user_id: int,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.2,
    ) -> dict[str, Any]:

        url = (
            f"{self.backend_url}"
            f"/api/model-connections/"
            f"{connection_id}/invoke"
        )
        headers = {
            "X-User-Id": str(user_id),
            "X-SmartOps-Internal-Token": self.internal_token,
            "Content-Type": "application/json",
        }
        payload = {
            "prompt": prompt,
            "systemPrompt": system_prompt,
            "temperature": temperature,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data: dict[str, Any] = response.json()
        except httpx.HTTPError as exc:
            raise ModelGatewayError(
                f"模型代理调用失败：{exc}"
            ) from exc

        return {
            "connection_id": data.get("connectionId", connection_id),
            "provider": data.get("provider", ""),
            "model": data.get("model", ""),
            "content": data.get("content", ""),
            "usage": data.get("usage", {}),
        }


__all__ = [
    "ModelGateway",
    "RuntimeModelConfig",
    "ModelGatewayError",
]
