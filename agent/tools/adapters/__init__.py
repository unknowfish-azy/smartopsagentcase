"""
SmartOps Tool Adapters.

Adapters 负责把外部能力适配到 SmartOps Tool 层。
"""

from .http import (
    HTTPToolAdapter,
    HTTPRequest,
    HTTPResponse,
    HTTPToolError,
    HTTPURLDenied,
)

from .mcp import (
    MCPTransport,
    MCPToolAdapter,
    MCPToolDefinition,
    MCPToolError,
    MCPToolNotFound,
)

from .python import (
    PythonToolAdapter,
    PythonToolResult,
    PythonToolError,
    PythonToolNotAllowed,
)

__all__ = [
    "HTTPToolAdapter",
    "HTTPRequest",
    "HTTPResponse",
    "HTTPToolError",
    "HTTPURLDenied",
    "MCPTransport",
    "MCPToolAdapter",
    "MCPToolDefinition",
    "MCPToolError",
    "MCPToolNotFound",
    "PythonToolAdapter",
    "PythonToolResult",
    "PythonToolError",
    "PythonToolNotAllowed",
]