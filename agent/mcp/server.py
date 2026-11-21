"""
SmartOps MCP Server（stdio）。

把 SmartOps 工具目录以 MCP `tools` 能力暴露给外部客户端（Claude Desktop /
Cursor / 自研 MCP 客户端等），并**完整复用既有执行链**：

    MCP tools/call
        → PlanStep + ExecutionContext
        → AgentExecutor.execute
        → 安全基线闸门（L0 合规 / L2 红线 / L1 限流）
        → PolicyEngine.authorize_execution（风险/审批）
        → 工具执行 → 审计落账

本模块**不得**绕过上述任何一层（与 `agent/tools/adapters/mcp.py` 的纪律一致）。

协议实现范围：`initialize` / `notifications/initialized` / `ping` /
`tools/list` / `tools/call`。其余方法返回 JSON-RPC `-32601`。
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep

from .catalog import ToolCatalog
from .protocol import (
    MCPError,
    MCPInternalError,
    MCPInvalidParams,
    MCPInvalidRequest,
    MCPMethodNotFound,
    MCP_PROTOCOL_VERSION,
    decode_message,
    is_notification,
    is_request,
    make_error,
    make_result,
    negotiate_protocol_version,
)

logger = logging.getLogger(__name__)


@dataclass
class MCPServerOptions:
    """服务端行为选项。"""

    server_name: str = "smartops-agent"
    version: str = "0.1.0"
    instructions: str = (
        "SmartOps 受控运维 Agent 的 MCP 接入点。"
        "所有工具调用都经过安全基线、风险与审批链，并被审计。"
    )
    # 默认 dry_run：MCP 客户端发起的调用先以演练态执行，
    # 需要真实执行必须显式打开（fail-safe）。
    dry_run: bool = True
    user_id: str = "mcp-client"
    environment: str = "default"


@dataclass
class MCPServerCapabilities:
    """服务端能力声明。"""

    tools_list_changed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tools": {
                "listChanged": self.tools_list_changed,
            }
        }


class SmartOpsMCPServer:
    """MCP 服务端。"""

    def __init__(
        self,
        executor,
        catalog: ToolCatalog,
        options: MCPServerOptions | None = None,
        capabilities: MCPServerCapabilities | None = None,
    ) -> None:
        self.executor = executor
        self.catalog = catalog
        self.options = options or MCPServerOptions()
        self.capabilities = (
            capabilities
            or MCPServerCapabilities()
        )
        self._initialized = False
        self._negotiated_version: str | None = None

    # ------------------------------------------------------------------
    # 消息处理
    # ------------------------------------------------------------------

    async def handle(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any] | None:
        """处理一条 JSON-RPC 消息；通知返回 None。"""

        if not isinstance(message, dict):
            return make_error(
                message_id=None,
                error=MCPInvalidRequest("消息必须是对象"),
            )

        method = message.get("method")
        message_id = message.get("id")

        if not method or not isinstance(method, str):
            if is_request(message):
                return make_error(
                    message_id=message_id,
                    error=MCPInvalidRequest("缺少 method"),
                )
            return None

        if is_notification(message):
            await self._handle_notification(method, message)
            return None

        if not is_request(message):
            # 响应类消息（服务端不该收到），忽略。
            return None

        # 初始化前只允许 initialize / ping。
        if not self._initialized and method not in (
            "initialize",
            "ping",
        ):
            return make_error(
                message_id=message_id,
                error=MCPInvalidRequest(
                    "客户端尚未完成 initialize 握手",
                ),
            )

        try:
            result = await self._dispatch(
                method,
                message,
            )
        except MCPError as exc:
            return make_error(
                message_id=message_id,
                error=exc,
            )
        except Exception as exc:  # noqa: BLE001 — 协议层兜底，绝不泄露堆栈
            logger.exception(
                "mcp server: 处理 %s 时发生内部错误",
                method,
            )
            return make_error(
                message_id=message_id,
                error=MCPInternalError(
                    f"内部错误：{type(exc).__name__}",
                ),
            )

        return make_result(
            message_id=message_id,
            result=result,
        )

    async def _dispatch(
        self,
        method: str,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        if method == "initialize":
            return self._handle_initialize(message)

        if method == "ping":
            return {}

        if method == "tools/list":
            return {"tools": self.catalog.list_tools()}

        if method == "tools/call":
            return await self._handle_tool_call(message)

        raise MCPMethodNotFound(
            f"未实现的方法：{method}",
        )

    async def _handle_notification(
        self,
        method: str,
        message: dict[str, Any],
    ) -> None:
        if method == "notifications/initialized":
            self._initialized = True
            logger.info("mcp server: 客户端已完成 initialize")
            return

        logger.debug(
            "mcp server: 忽略通知 %s",
            method,
        )

    # ------------------------------------------------------------------
    # initialize
    # ------------------------------------------------------------------

    def _handle_initialize(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        params = message.get("params") or {}

        if not isinstance(params, dict):
            raise MCPInvalidParams("initialize params 必须是对象")

        negotiated, matches_request = (
            negotiate_protocol_version(
                params.get("protocolVersion")
            )
        )

        self._negotiated_version = negotiated

        if not matches_request:
            logger.info(
                "mcp server: 客户端请求协议版本 %r 不受支持，"
                "协商为 %s",
                params.get("protocolVersion"),
                negotiated,
            )

        client_info = params.get("clientInfo") or {}

        return {
            "protocolVersion": negotiated,
            "capabilities": (
                self.capabilities.to_dict()
            ),
            "serverInfo": {
                "name": self.options.server_name,
                "version": self.options.version,
            },
            "instructions": self.options.instructions,
        }

    # ------------------------------------------------------------------
    # tools/call
    # ------------------------------------------------------------------

    async def _handle_tool_call(
        self,
        message: dict[str, Any],
    ) -> dict[str, Any]:
        params = message.get("params") or {}

        if not isinstance(params, dict):
            raise MCPInvalidParams("tools/call params 必须是对象")

        name = params.get("name")

        if not name or not isinstance(name, str):
            raise MCPInvalidParams("tools/call 缺少 name")

        entry = self.catalog.get(name)

        if entry is None:
            raise MCPInvalidParams(
                f"未暴露的工具：{name}",
                data={
                    "exposed": [
                        item.name
                        for item in self.catalog.list_entries()
                    ],
                },
            )

        arguments = params.get("arguments") or {}

        if not isinstance(arguments, dict):
            raise MCPInvalidParams(
                "tools/call arguments 必须是对象"
            )

        result = await asyncio.to_thread(
            self._run_tool,
            entry,
            arguments,
        )

        text = _result_to_text(result)

        return {
            "content": [
                {
                    "type": "text",
                    "text": text,
                }
            ],
            "isError": not result.success,
        }

    def _run_tool(
        self,
        entry,
        arguments: dict[str, Any],
    ):
        """在 executor 的安全链内执行一次工具调用。"""

        context = ExecutionContext(
            request_id=f"mcp-{uuid4().hex}",
            user_id=self.options.user_id,
            environment=self.options.environment,
            dry_run=self.options.dry_run,
            metadata={
                "source": "mcp",
                "tool": entry.name,
            },
        )

        step = PlanStep(
            step_id=1,
            action=f"MCP 调用 {entry.name}",
            tool_name=entry.name,
            arguments=arguments,
            description=(
                f"由 MCP 客户端发起：{entry.name}"
            ),
            requires_approval=False,
        )

        logger.info(
            "mcp server: 调用工具 %s（dry_run=%s）",
            entry.name,
            self.options.dry_run,
        )

        return self.executor.execute(
            step,
            context,
        )

    # ------------------------------------------------------------------
    # 服务循环
    # ------------------------------------------------------------------

    async def serve(
        self,
        transport,
    ) -> None:
        """从 transport 逐条读取并处理，直到 EOF。"""

        while True:
            line = await asyncio.to_thread(
                transport.read_line,
            )

            if line is None:
                logger.info("mcp server: stdin 关闭，退出")
                break

            if not line.strip():
                continue

            try:
                message = decode_message(line)
            except MCPError as exc:
                transport.write_message(
                    make_error(
                        message_id=None,
                        error=exc,
                    )
                )
                continue

            response = await self.handle(message)

            if response is not None:
                transport.write_message(response)


def _result_to_text(result: Any) -> str:
    """把 ExecutionResult 序列化成 MCP 文本内容。"""

    output = getattr(result, "output", None)

    if output is None:
        output = {
            "message": getattr(result, "message", None),
            "error": getattr(result, "error", None),
        }

    if isinstance(output, str):
        return output

    try:
        return json.dumps(
            output,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        return str(output)


__all__ = [
    "MCPServerCapabilities",
    "MCPServerOptions",
    "SmartOpsMCPServer",
]
