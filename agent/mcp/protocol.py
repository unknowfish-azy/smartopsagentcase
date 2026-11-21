"""
SmartOps MCP 协议层（JSON-RPC 2.0 + Model Context Protocol）。

本模块只负责**消息形状与编解码**，不含任何传输/执行语义：

    - JSON-RPC 2.0 请求 / 通知 / 响应 / 错误
    - MCP 协议版本与标准错误码
    - stdio 分帧纪律：一条消息 = 一行 UTF-8 JSON，**不得包含内嵌换行**

设计约束（与既有 `agent/tools/adapters/mcp.py` 的 Transport 抽象配套）：
核心 Harness 不依赖任何 MCP SDK 版本，协议以最小可读实现自持，
便于逐字节审计与测试。
"""

from __future__ import annotations

import json
from typing import Any

# ------------------------------------------------------------------
# 协议版本
# ------------------------------------------------------------------

MCP_PROTOCOL_VERSION = "2025-03-26"

# 服务端声明支持的版本，按"最新优先"排列。
# 版本协商规则（spec lifecycle）：客户端请求支持的版本若在其中，原样返回；
# 否则返回服务端最新支持版本，由客户端决定是否断开。
SUPPORTED_PROTOCOL_VERSIONS: tuple[str, ...] = (
    "2025-03-26",
    "2024-11-05",
)

# ------------------------------------------------------------------
# JSON-RPC 2.0 标准错误码
# ------------------------------------------------------------------

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class MCPError(Exception):
    """MCP / JSON-RPC 错误。

    与 JSON-RPC 响应中的 `error` 对象一一对应（code / message / data）。
    """

    code: int = INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        data: Any | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.data = data

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if self.data is not None:
            payload["data"] = self.data
        return payload


class MCPParseError(MCPError):
    """收到无法解析为 JSON 的消息。"""

    code = PARSE_ERROR


class MCPInvalidRequest(MCPError):
    """消息不是合法的 JSON-RPC 请求/通知。"""

    code = INVALID_REQUEST


class MCPMethodNotFound(MCPError):
    """方法未实现。"""

    code = METHOD_NOT_FOUND


class MCPInvalidParams(MCPError):
    """方法参数非法。"""

    code = INVALID_PARAMS


class MCPInternalError(MCPError):
    """服务端内部错误。"""

    code = INTERNAL_ERROR


# ------------------------------------------------------------------
# 消息构造
# ------------------------------------------------------------------

JSONRPC_VERSION = "2.0"


def make_request(
    *,
    message_id: int | str,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 JSON-RPC 请求。"""

    message: dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "id": message_id,
        "method": method,
    }
    if params is not None:
        message["params"] = params
    return message


def make_notification(
    *,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造 JSON-RPC 通知（无 id，不期待响应）。"""

    message: dict[str, Any] = {
        "jsonrpc": JSONRPC_VERSION,
        "method": method,
    }
    if params is not None:
        message["params"] = params
    return message


def make_result(
    *,
    message_id: int | str | None,
    result: dict[str, Any] | list[Any] | None = None,
) -> dict[str, Any]:
    """构造 JSON-RPC 成功响应。"""

    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": message_id,
        "result": {} if result is None else result,
    }


def make_error(
    *,
    message_id: int | str | None,
    error: MCPError,
) -> dict[str, Any]:
    """构造 JSON-RPC 错误响应。"""

    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": message_id,
        "error": error.to_dict(),
    }


# ------------------------------------------------------------------
# 编解码（stdio 分帧纪律）
# ------------------------------------------------------------------

def encode_message(
    message: dict[str, Any],
) -> str:
    """把消息编码成**单行** UTF-8 JSON。

    关键：MCP stdio 传输以换行分帧，消息内部**不得包含内嵌换行**。
    这里用紧凑分隔符并显式拒绝 NaN/Infinity（它们不是合法 JSON），
    避免对端解析失败。
    """

    return json.dumps(
        message,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )


def decode_message(
    line: str,
) -> dict[str, Any]:
    """解析一行 JSON-RPC 消息。

    抛 `MCPParseError`：空行或非法 JSON。
    抛 `MCPInvalidRequest`：不是对象。
    """

    text = line.strip()

    if not text:
        raise MCPParseError("空行不是合法的 JSON-RPC 消息")

    try:
        payload = json.loads(text)
    except (ValueError, TypeError) as exc:
        raise MCPParseError(
            f"无法解析为 JSON：{exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise MCPInvalidRequest(
            "JSON-RPC 消息必须是对象"
        )

    return payload


def is_request(
    message: dict[str, Any],
) -> bool:
    """判断是否为请求（含 id + method）。"""

    return (
        "method" in message
        and "id" in message
    )


def is_notification(
    message: dict[str, Any],
) -> bool:
    """判断是否为通知（含 method，不含 id）。"""

    return (
        "method" in message
        and "id" not in message
    )


def is_response(
    message: dict[str, Any],
) -> bool:
    """判断是否为响应（含 id，含 result 或 error，不含 method）。"""

    return (
        "id" in message
        and "method" not in message
        and ("result" in message or "error" in message)
    )


def negotiate_protocol_version(
    requested: Any,
) -> tuple[str, bool]:
    """版本协商。

    返回 `(服务端将使用的协议版本, 是否与客户端请求一致)`。

    规则（spec lifecycle）：
        客户端请求版本被支持 -> 原样返回（一致）；
        否则 -> 返回服务端最新支持版本（不一致，由客户端决定是否断开）。
    """

    requested_text = (
        requested
        if isinstance(requested, str)
        else ""
    )

    if requested_text in SUPPORTED_PROTOCOL_VERSIONS:
        return requested_text, True

    return MCP_PROTOCOL_VERSION, False


__all__ = [
    "JSONRPC_VERSION",
    "INTERNAL_ERROR",
    "INVALID_PARAMS",
    "INVALID_REQUEST",
    "MCPError",
    "MCPInternalError",
    "MCPInvalidParams",
    "MCPInvalidRequest",
    "MCPMethodNotFound",
    "MCPParseError",
    "MCP_PROTOCOL_VERSION",
    "METHOD_NOT_FOUND",
    "PARSE_ERROR",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "decode_message",
    "encode_message",
    "is_notification",
    "is_request",
    "is_response",
    "make_error",
    "make_notification",
    "make_request",
    "make_result",
    "negotiate_protocol_version",
]
