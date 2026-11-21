"""MCP 端到端：真实子进程 server + 客户端握手 + tools/list + tools/call。

验证 stdout 分帧纪律（客户端只解析到合法 JSON-RPC）、版本协商、
以及 dry-run 下的工具调用链路。
"""

import os
import sys
from pathlib import Path

import pytest

from agent.mcp.client import MCPClient
from agent.mcp.protocol import MCP_PROTOCOL_VERSION
from agent.mcp.transport import StdioClientTransport

REPO = Path(__file__).resolve().parents[3]


def _server_command(*extra: str) -> list[str]:
    return [
        sys.executable,
        "-m",
        "agent.mcp",
        "--dry-run",
        *extra,
    ]


async def _connect(command: list[str]) -> MCPClient:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get(
        "PYTHONPATH",
        "",
    )

    transport = StdioClientTransport(command, env=env)
    client = MCPClient(transport)
    await client.connect()
    return client


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_server_handshake_and_tool_list():
    client = await _connect(_server_command())

    try:
        assert client.initialize_result is not None
        assert (
            client.initialize_result.protocol_version
            == MCP_PROTOCOL_VERSION
        )
        assert (
            client.initialize_result.server_name
            == "smartops-agent"
        )

        tools = await client.list_tools()
        names = [tool.name for tool in tools]

        assert "nginx.status" in names
        assert "redis.info" in names
        # 写操作默认不得暴露
        assert "redis.restart" not in names
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_server_tool_call_dry_run():
    client = await _connect(_server_command())

    try:
        result = await client.call_tool("nginx.status", {})

        assert result.get("isError") is False
        assert result.get("content")
    finally:
        await client.close()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_server_rejects_request_before_initialize():
    """未握手就发 tools/list 应被服务端拒绝。"""

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get(
        "PYTHONPATH",
        "",
    )

    transport = StdioClientTransport(
        _server_command(),
        env=env,
    )
    await transport.start()

    try:
        response = await transport.request("tools/list", {})

        assert response["error"]["code"] == -32600
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_client_adapter_bridges_external_tools():
    """MCPClient 产出的 MCPToolAdapter 可被发现与调用。"""

    client = await _connect(_server_command())

    try:
        adapter = client.as_tool_adapter(server_name="smartops")

        discovered = await adapter.discover()
        names = [tool.name for tool in discovered]

        assert "nginx.status" in names

        result = await adapter.call("nginx.status", {})
        assert result.get("isError") is False
    finally:
        await client.close()
