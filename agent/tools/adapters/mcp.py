"""
SmartOps MCP Tool Adapter.

用于将外部 MCP Server 提供的 Tool
适配到 SmartOps Tool 层。

当前版本采用 Transport 抽象：

    MCP Tool
       ↓
    MCPTransport
       ↓
    External MCP Server

这样可以避免让核心 Harness 强依赖某一个 MCP SDK 版本。

重要：

MCP Tool 仍然需要经过：

    Permission
    Risk
    SafeAgent
    Sandbox
    Verification
    Audit

本 Adapter 不得绕过这些安全层。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class MCPToolError(RuntimeError):
    """MCP Tool 基础异常。"""


class MCPToolNotFound(MCPToolError):
    """MCP Tool 不存在。"""


@dataclass(slots=True)
class MCPToolDefinition:
    """
    外部 MCP Tool 描述。
    """

    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(
        default_factory=dict
    )
    server: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
            "server": self.server,
        }


class MCPTransport(Protocol):
    """
    MCP Transport 抽象。

    具体实现可以对接：

    - stdio
    - HTTP
    - SSE
    - 其他受支持 transport
    """

    async def list_tools(
        self,
    ) -> list[dict[str, Any]]:
        ...

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> Any:
        ...


class MCPToolAdapter:
    """
    MCP Tool Adapter。
    """

    def __init__(
        self,
        *,
        transport: MCPTransport,
        server_name: str = "mcp",
    ) -> None:
        self.transport = transport
        self.server_name = server_name

        self._tools: dict[
            str,
            MCPToolDefinition,
        ] = {}

    async def discover(self) -> list[MCPToolDefinition]:
        """
        从 MCP Server 发现 Tool。
        """
        raw_tools = await self.transport.list_tools()

        discovered: list[
            MCPToolDefinition
        ] = []

        for raw in raw_tools:
            name = str(
                raw.get("name", "")
            ).strip()

            if not name:
                continue

            tool = MCPToolDefinition(
                name=name,
                description=str(
                    raw.get(
                        "description",
                        "",
                    )
                ),
                input_schema=dict(
                    raw.get(
                        "inputSchema",
                        raw.get(
                            "input_schema",
                            {},
                        ),
                    )
                ),
                server=self.server_name,
            )

            self._tools[name] = tool
            discovered.append(tool)

        return discovered

    async def call(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """
        调用 MCP Tool。
        """
        if name not in self._tools:
            # 允许调用前重新发现。
            await self.discover()

        if name not in self._tools:
            raise MCPToolNotFound(
                f"MCP Tool 未找到：{name}"
            )

        return await self.transport.call_tool(
            name,
            arguments or {},
        )

    def get(
        self,
        name: str,
    ) -> MCPToolDefinition | None:
        """
        获取 MCP Tool 定义。
        """
        return self._tools.get(name)

    def list_tools(
        self,
    ) -> list[MCPToolDefinition]:
        """
        返回已发现 Tool。
        """
        return sorted(
            self._tools.values(),
            key=lambda item: item.name,
        )


__all__ = [
    "MCPTransport",
    "MCPToolAdapter",
    "MCPToolDefinition",
    "MCPToolError",
    "MCPToolNotFound",
]