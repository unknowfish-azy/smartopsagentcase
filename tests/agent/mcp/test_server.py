"""SmartOps MCP 服务端单测：握手、能力声明、tools/list、tools/call、安全链复用。"""

import asyncio

import pytest

from agent.executor.executor import AgentExecutor
from agent.mcp.catalog import ToolCatalog
from agent.mcp.protocol import (
    MCP_PROTOCOL_VERSION,
    make_notification,
    make_request,
)
from agent.mcp.server import MCPServerOptions, SmartOpsMCPServer
from agent.policies.policy_engine import PolicyEngine
from agent.policies.risk import RiskLevel
from agent.registry.tool_registry import ToolRegistry
from agent.sdk.tool import PluginTool, ToolDefinition
from agent.tools.registry import ToolRegistry as ExecutorToolRegistry


class EchoTool(PluginTool):
    definition = ToolDefinition(
        name="demo.echo",
        description="回显参数",
        risk=RiskLevel.LOW,
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
        },
    )

    async def execute(self, arguments, context):
        return {"echo": arguments.get("text")}


class ExplodeTool(PluginTool):
    definition = ToolDefinition(
        name="demo.explode",
        description="执行报错",
        risk=RiskLevel.LOW,
    )

    async def execute(self, arguments, context):
        raise RuntimeError("boom")


def _build_server(
    *,
    dry_run: bool = True,
) -> tuple[SmartOpsMCPServer, AgentExecutor]:
    plugin_registry = ToolRegistry()
    plugin_registry.register(EchoTool())
    plugin_registry.register(ExplodeTool())

    executor_registry = ExecutorToolRegistry()
    executor_registry.register(EchoTool())
    executor_registry.register(ExplodeTool())

    executor = AgentExecutor(executor_registry, PolicyEngine())

    catalog = ToolCatalog.from_registry(
        plugin_registry,
        allowlist=["demo.echo", "demo.explode"],
    )

    server = SmartOpsMCPServer(
        executor,
        catalog,
        options=MCPServerOptions(dry_run=dry_run),
    )

    return server, executor


async def _initialize(server: SmartOpsMCPServer) -> dict:
    response = await server.handle(
        make_request(
            message_id=1,
            method="initialize",
            params={
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        )
    )
    await server.handle(
        make_notification(
            method="notifications/initialized"
        )
    )
    return response


@pytest.mark.asyncio
async def test_initialize_returns_capabilities_and_server_info():
    server, _ = _build_server()

    response = await _initialize(server)

    result = response["result"]
    assert result["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert result["capabilities"]["tools"] == {"listChanged": False}
    assert result["serverInfo"]["name"] == "smartops-agent"


@pytest.mark.asyncio
async def test_initialize_negotiates_unsupported_version():
    server, _ = _build_server()

    response = await server.handle(
        make_request(
            message_id=1,
            method="initialize",
            params={
                "protocolVersion": "1999-01-01",
                "capabilities": {},
                "clientInfo": {"name": "pytest", "version": "0"},
            },
        )
    )

    assert response["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION


@pytest.mark.asyncio
async def test_request_before_initialize_is_rejected():
    server, _ = _build_server()

    response = await server.handle(
        make_request(
            message_id=2,
            method="tools/list",
            params={},
        )
    )

    assert response["error"]["code"] == -32600


@pytest.mark.asyncio
async def test_ping_works_before_initialize():
    server, _ = _build_server()

    response = await server.handle(
        make_request(
            message_id=3,
            method="ping",
        )
    )

    assert response["result"] == {}


@pytest.mark.asyncio
async def test_unknown_method_returns_method_not_found():
    server, _ = _build_server()
    await _initialize(server)

    response = await server.handle(
        make_request(
            message_id=4,
            method="resources/list",
            params={},
        )
    )

    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_tools_list_returns_catalog():
    server, _ = _build_server()
    await _initialize(server)

    response = await server.handle(
        make_request(
            message_id=5,
            method="tools/list",
            params={},
        )
    )

    names = [tool["name"] for tool in response["result"]["tools"]]

    assert names == ["demo.echo", "demo.explode"]


@pytest.mark.asyncio
async def test_tools_call_unknown_tool_is_invalid_params():
    server, _ = _build_server()
    await _initialize(server)

    response = await server.handle(
        make_request(
            message_id=6,
            method="tools/call",
            params={"name": "demo.missing", "arguments": {}},
        )
    )

    assert response["error"]["code"] == -32602
    assert "demo.missing" in response["error"]["message"]


@pytest.mark.asyncio
async def test_tools_call_dry_run_returns_content():
    server, _ = _build_server(dry_run=True)
    await _initialize(server)

    response = await server.handle(
        make_request(
            message_id=7,
            method="tools/call",
            params={
                "name": "demo.echo",
                "arguments": {"text": "hello"},
            },
        )
    )

    result = response["result"]
    assert result["isError"] is False
    assert len(result["content"]) == 1
    assert result["content"][0]["type"] == "text"

    import json

    payload = json.loads(result["content"][0]["text"])
    assert payload == {"text": "hello"}


@pytest.mark.asyncio
async def test_tools_call_execution_error_sets_is_error():
    server, _ = _build_server(dry_run=False)
    await _initialize(server)

    response = await server.handle(
        make_request(
            message_id=8,
            method="tools/call",
            params={"name": "demo.explode", "arguments": {}},
        )
    )

    assert response["result"]["isError"] is True


@pytest.mark.asyncio
async def test_tool_invocation_goes_through_executor():
    """MCP 调用必须经过 executor（留下 run event），不得绕过安全链。"""

    server, executor = _build_server(dry_run=True)
    await _initialize(server)

    before = len(executor.get_run_events())

    await server.handle(
        make_request(
            message_id=9,
            method="tools/call",
            params={
                "name": "demo.echo",
                "arguments": {"text": "audited"},
            },
        )
    )

    events = executor.get_run_events()
    assert len(events) > before
    assert events[-1]["status"] == "dry_run"
    assert events[-1]["source"] == "executor"
