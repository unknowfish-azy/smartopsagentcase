"""
SmartOps MCP Client。

把外部 MCP server 接入 SmartOps 工具层：

    MCPClient
      → StdioClientTransport（连外部 server）
      → initialize 握手（版本协商）
      → list_tools / call_tool
      → 产出既有 MCPToolAdapter（agent/tools/adapters/mcp.py）

这样外部 MCP 工具可以像原生插件工具一样，被 executor 的
Permission / Risk / SafeAgent / Audit 链统一管辖。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from agent.tools.adapters.mcp import (
    MCPToolAdapter,
    MCPToolDefinition,
    MCPToolError,
)

from .protocol import (
    MCPError,
    MCPInternalError,
    MCPInvalidParams,
    MCP_PROTOCOL_VERSION,
    make_request,
)
from .transport import StdioClientTransport

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MCPInitializeResult:
    """initialize 握手结果。"""

    protocol_version: str
    server_name: str
    server_version: str
    instructions: str = ""


class _ClientTransportAdapter:
    """把 MCPClient 适配成 `MCPTransport` Protocol。"""

    def __init__(
        self,
        client: "MCPClient",
    ) -> None:
        self._client = client

    async def list_tools(self) -> list[dict[str, Any]]:
        # MCPToolAdapter 期望原始 MCP Tool 对象（dict），
        # 而不是已转换的 MCPToolDefinition。
        return await self._client.list_raw_tools()

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        return await self._client.call_tool(
            name,
            arguments,
        )


class MCPClient:
    """外部 MCP server 客户端。"""

    def __init__(
        self,
        transport: StdioClientTransport,
        *,
        client_name: str = "smartops-agent",
        client_version: str = "0.1.0",
        protocol_version: str = MCP_PROTOCOL_VERSION,
    ) -> None:
        self.transport = transport
        self.client_name = client_name
        self.client_version = client_version
        self.protocol_version = protocol_version
        self.initialize_result: MCPInitializeResult | None = None
        self._request_seq = 0

    # ------------------------------------------------------------------

    async def connect(self) -> MCPInitializeResult:
        """启动传输并完成 initialize 握手。"""

        await self.transport.start()

        response = await self._request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": self.client_name,
                    "version": self.client_version,
                },
            },
        )

        result = response.get("result") or {}

        self.initialize_result = MCPInitializeResult(
            protocol_version=str(
                result.get(
                    "protocolVersion",
                    self.protocol_version,
                )
            ),
            server_name=str(
                (result.get("serverInfo") or {}).get(
                    "name",
                    "unknown",
                )
            ),
            server_version=str(
                (result.get("serverInfo") or {}).get(
                    "version",
                    "unknown",
                )
            ),
            instructions=str(
                result.get("instructions", "")
                or ""
            ),
        )

        await self.transport.notify(
            "notifications/initialized"
        )

        logger.info(
            "mcp client: 已连接 %s@%s（协议 %s）",
            self.initialize_result.server_name,
            self.initialize_result.server_version,
            self.initialize_result.protocol_version,
        )

        return self.initialize_result

    async def list_raw_tools(self) -> list[dict[str, Any]]:
        """返回 `tools/list` 的原始 Tool 对象（供 MCPTransport 适配）。"""

        response = await self._request("tools/list", {})

        raw_tools = (response.get("result") or {}).get(
            "tools",
            [],
        )

        return [
            item
            for item in raw_tools
            if isinstance(item, dict)
        ]

    async def list_tools(self) -> list[MCPToolDefinition]:
        """发现外部 server 的工具。"""

        raw_tools = await self.list_raw_tools()

        discovered: list[MCPToolDefinition] = []

        for raw in raw_tools:
            if not isinstance(raw, dict):
                continue

            name = str(raw.get("name", "")).strip()

            if not name:
                continue

            discovered.append(
                MCPToolDefinition(
                    name=name,
                    description=str(
                        raw.get("description", "")
                        or ""
                    ),
                    input_schema=dict(
                        raw.get("inputSchema", {})
                        or raw.get("input_schema", {})
                        or {}
                    ),
                    server=(
                        self.initialize_result.server_name
                        if self.initialize_result
                        else "mcp"
                    ),
                )
            )

        return discovered

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """调用外部工具，返回 CallToolResult。"""

        if not name:
            raise MCPInvalidParams("工具名不能为空")

        response = await self._request(
            "tools/call",
            {
                "name": name,
                "arguments": dict(arguments or {}),
            },
        )

        return response.get("result") or {}

    def as_tool_adapter(
        self,
        *,
        server_name: str = "mcp",
    ) -> MCPToolAdapter:
        """产出既有 `MCPToolAdapter`，供 SmartOps 工具层使用。"""

        return MCPToolAdapter(
            transport=_ClientTransportAdapter(self),
            server_name=server_name,
        )

    async def close(self) -> None:
        await self.transport.close()

    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_seq += 1
        return self._request_seq

    async def _request(
        self,
        method: str,
        params: dict[str, Any] | None,
    ) -> dict[str, Any]:
        response = await self.transport.request(
            method,
            params,
            message_id=self._next_id(),
        )

        error = response.get("error")

        if error:
            raise MCPToolError(
                str(error.get("message") or "MCP 调用失败"),
            )

        if "result" not in response:
            raise MCPInternalError(
                "MCP 响应缺少 result 字段",
            )

        return response


__all__ = [
    "MCPClient",
    "MCPInitializeResult",
]
