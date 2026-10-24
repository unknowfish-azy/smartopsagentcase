"""
SmartOps Builtin Server Tool.

负责 SmartOps Server 的基础信息查询：

    - Server List
    - Server Detail
    - Server Metrics
    - Latest Metrics

对应 Backend：

    GET /api/servers
    GET /api/servers/{id}
    GET /api/servers/{serverId}/metrics
    GET /api/servers/{serverId}/metrics/latest

该 Tool 默认只提供查询能力。

创建 / 修改 / 删除服务器
应通过独立 Tool，并由：

    Permission
    Risk
    Approval
    SafeAgent

控制。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class ServerToolError(RuntimeError):
    """Server Tool 基础异常。"""


@dataclass(slots=True)
class ServerToolConfig:
    """
    Server API 配置。
    """

    base_url: str = (
        "http://127.0.0.1:8080"
    )

    timeout: float = 10.0


class ServerTool:
    """
    SmartOps Server Query Tool。
    """

    def __init__(
        self,
        config: ServerToolConfig | None = None,
    ) -> None:
        self.config = (
            config
            or ServerToolConfig()
        )

        self.base_url = (
            self.config.base_url.rstrip("/")
        )

    async def list_servers(
        self,
        *,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """
        查询 Server 列表。
        """
        if page <= 0:
            raise ServerToolError(
                "page 必须大于 0"
            )

        if size <= 0 or size > 100:
            raise ServerToolError(
                "size 必须在 1 到 100 之间"
            )

        return await self._get(
            "/api/servers",
            params={
                "page": page,
                "size": size,
            },
        )

    async def get_server(
        self,
        server_id: int,
    ) -> dict[str, Any]:
        """
        查询单台 Server。
        """
        self._validate_id(
            server_id
        )

        return await self._get(
            f"/api/servers/{server_id}"
        )

    async def latest_metrics(
        self,
        server_id: int,
    ) -> dict[str, Any]:
        """
        查询最新指标。
        """
        self._validate_id(
            server_id
        )

        return await self._get(
            (
                f"/api/servers/"
                f"{server_id}/metrics/latest"
            )
        )

    async def metrics(
        self,
        server_id: int,
        *,
        page: int = 1,
        size: int = 20,
    ) -> dict[str, Any]:
        """
        查询历史指标。
        """
        self._validate_id(
            server_id
        )

        return await self._get(
            (
                f"/api/servers/"
                f"{server_id}/metrics"
            ),
            params={
                "page": page,
                "size": size,
            },
        )

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = (
            f"{self.base_url}{path}"
        )

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout
            ) as client:
                response = await client.get(
                    url,
                    params=params,
                )

                response.raise_for_status()

        except httpx.HTTPError as exc:
            raise ServerToolError(
                f"Server API 请求失败：{exc}"
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise ServerToolError(
                "Server API 返回的数据不是 JSON"
            ) from exc

        if isinstance(data, dict):
            return data

        return {
            "data": data
        }

    @staticmethod
    def _validate_id(
        server_id: int,
    ) -> None:
        if not isinstance(
            server_id,
            int,
        ):
            raise ServerToolError(
                "server_id 必须为整数"
            )

        if server_id <= 0:
            raise ServerToolError(
                "server_id 必须大于 0"
            )


__all__ = [
    "ServerTool",
    "ServerToolConfig",
    "ServerToolError",
]