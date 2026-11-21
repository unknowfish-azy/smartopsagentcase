"""
SmartOps MCP 子系统。

两部分能力：

    * **Server**：把 SmartOps 工具目录暴露为 MCP 服务端（stdio），
      供外部 MCP 客户端调用；执行完整复用 AgentExecutor 安全链。
    * **Client**：连接外部 MCP server，并适配成既有 `MCPToolAdapter`，
      让外部工具进入 SmartOps 工具层。

协议实现范围：JSON-RPC 2.0 + MCP `initialize` / `ping` / `tools/list` /
`tools/call`，stdio 传输。
"""

from .catalog import CatalogEntry, ToolCatalog
from .client import MCPClient, MCPInitializeResult
from .protocol import (
    MCPError,
    MCPInternalError,
    MCPInvalidParams,
    MCPInvalidRequest,
    MCPMethodNotFound,
    MCPParseError,
    MCP_PROTOCOL_VERSION,
    SUPPORTED_PROTOCOL_VERSIONS,
)
from .server import (
    MCPServerCapabilities,
    MCPServerOptions,
    SmartOpsMCPServer,
)
from .transport import StdioClientTransport, StdioServerTransport

__all__ = [
    "CatalogEntry",
    "MCPClient",
    "MCPError",
    "MCPInternalError",
    "MCPInitializeResult",
    "MCPInvalidParams",
    "MCPInvalidRequest",
    "MCPServerCapabilities",
    "MCPServerOptions",
    "MCPMethodNotFound",
    "MCPParseError",
    "MCP_PROTOCOL_VERSION",
    "SmartOpsMCPServer",
    "StdioClientTransport",
    "StdioServerTransport",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "ToolCatalog",
]
