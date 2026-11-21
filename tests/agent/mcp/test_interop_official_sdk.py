"""官方 MCP SDK 互操作测试（可选）。

默认跳过：主环境不安装官方 `mcp` SDK，避免把可选依赖变成硬依赖。

启用方式（隔离安装，不污染主环境）：

    py -3.14 -m pip install --target .runtime/mcp-sdk mcp
    MCP_SDK_PATH=.runtime/mcp-sdk py -3.14 -m pytest \\
        tests/agent/mcp/test_interop_official_sdk.py -v

验证目标：我们的 stdio server 能被**标准 MCP 客户端**发现并调用。
这是"MCP 能力"从骨架升级为可互操作协议的外部证据。
"""

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
_SDK_PATH = os.environ.get("MCP_SDK_PATH")


@pytest.fixture
def mcp_sdk():
    if not _SDK_PATH:
        pytest.skip(
            "未设置 MCP_SDK_PATH（官方 mcp SDK 未隔离安装）"
        )

    sdk_path = Path(_SDK_PATH)
    if not sdk_path.exists():
        pytest.skip(f"MCP_SDK_PATH 不存在：{sdk_path}")

    sys.path.insert(0, str(sdk_path))
    try:
        yield
    finally:
        try:
            sys.path.remove(str(sdk_path))
        except ValueError:
            pass


@pytest.mark.asyncio
@pytest.mark.e2e
async def test_official_sdk_can_initialize_list_and_call(mcp_sdk):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get(
        "PYTHONPATH",
        "",
    )

    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agent.mcp", "--dry-run"],
        cwd=str(REPO),
        env=env,
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()

            assert initialized.server_info.name == "smartops-agent"

            tools = await session.list_tools()
            names = [tool.name for tool in tools.tools]

            assert "nginx.status" in names
            assert "redis.restart" not in names

            result = await session.call_tool("nginx.status", {})

            assert result.is_error is False
