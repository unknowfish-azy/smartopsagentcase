"""W3 验收：Product Tool Bus 只读 12 工具。

覆盖：
1. 工具注册表恰好 12 个、全部只读低风险、零审批；
2. 每个工具声明的 METHOD/Path 与后端控制器契约一致；
3. 真实调用路径、参数拼装与 ApiResponse 信封解包；
4. 身份透传：用户会话头优先，系统 token 不叠加，未知头丢弃；
5. 越权 403 → PERMISSION（fatal），5xx → NETWORK（可重试）；
6. audit.chain 同时返回后端审计与本地哈希链校验结果。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.executor.models import ExecutionContext  # noqa: E402
from agent.policies.risk import RiskLevel  # noqa: E402
from agent.tools.builtin.product_bus import (  # noqa: E402
    ProductApiClient,
    READ_TOOL_METAS,
    build_product_read_tools,
)
from agent.tools.errors import ToolErrorCategory, ToolExecutionError  # noqa: E402

# 后端控制器契约快照：改动路径必须先改这里，防止"工具指向不存在的接口"。
EXPECTED_CONTRACT = {
    "sentinel.alerts": ("GET", "/api/sentinel/alerts"),
    "sentinel.metrics": ("GET", "/api/servers/{serverId}/metrics/latest"),
    "inspector.events": ("GET", "/api/inspector/events"),
    "knowledge.search": ("POST", "/api/search"),
    "knowledge.candidates": ("GET", "/api/knowledge/candidates"),
    "security.posture": ("GET", "/api/security/summary"),
    "security.findings": ("GET", "/api/security/summary"),
    "servers.list": ("GET", "/api/servers"),
    "slo.status": ("GET", "/api/observability/slo"),
    "incidents.list": ("GET", "/api/incidents"),
    "robot.fleet": ("GET", "/api/robot/fleet/status"),
    "audit.chain": ("GET", "/api/admin/audit"),
}


def _ctx(metadata: dict | None = None) -> ExecutionContext:
    return ExecutionContext(request_id="req_w3", user_id="u1", metadata=metadata or {})


def _client(handler, **kwargs) -> ProductApiClient:
    return ProductApiClient(
        backend_base_url="http://backend.test",
        knowledge_base_url="http://knowledge.test",
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _tool(client: ProductApiClient, name: str, **kwargs):
    return {tool.name: tool for tool in build_product_read_tools(client=client, **kwargs)}[name]


def test_registry_exposes_exactly_twelve_readonly_tools():
    tools = build_product_read_tools(client=_client(lambda request: httpx.Response(200, json={"data": []})))

    assert len(tools) == 12
    assert {tool.name for tool in tools} == set(EXPECTED_CONTRACT)
    for tool in tools:
        assert tool.definition.risk is RiskLevel.LOW
        assert tool.definition.required_scope
        assert tool.requires_approval is False
        assert tool.definition.implementation_status.value == "REAL"


@pytest.mark.parametrize("meta", READ_TOOL_METAS, ids=lambda meta: meta.name)
def test_declared_paths_match_backend_contract(meta):
    assert (meta.method, meta.path) == EXPECTED_CONTRACT[meta.name]


def test_sentinel_alerts_calls_real_path_and_unwraps_envelope():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "message": "", "data": [{"id": 1, "level": "P1"}]})

    result = asyncio.run(_tool(_client(handler), "sentinel.alerts").execute({}, _ctx()))

    assert result["ok"] is True
    assert result["source"] == "/api/sentinel/alerts"
    assert result["count"] == 1
    assert result["data"] == [{"id": 1, "level": "P1"}]
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/sentinel/alerts"


def test_sentinel_metrics_builds_server_path():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"cpu": 0.42}})

    result = asyncio.run(
        _tool(_client(handler), "sentinel.metrics").execute({"serverId": 7}, _ctx())
    )

    assert seen[0].url.path == "/api/servers/7/metrics/latest"
    assert result["data"] == {"cpu": 0.42}


def test_metrics_without_server_id_is_parameter_error():
    tool = _tool(_client(lambda request: httpx.Response(200, json={"data": None})), "sentinel.metrics")

    with pytest.raises(ToolExecutionError) as excinfo:
        asyncio.run(tool.execute({}, _ctx()))

    assert excinfo.value.category is ToolErrorCategory.PARAMETER


def test_knowledge_search_posts_body_to_knowledge_service():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"items": [{"title": "nginx 502"}]})

    result = asyncio.run(
        _tool(_client(handler), "knowledge.search").execute(
            {"query": "nginx 502", "top_k": 3}, _ctx()
        )
    )

    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == "http://knowledge.test/api/search"
    assert json.loads(request.content) == {"query": "nginx 502", "top_k": 3}
    assert result["data"] == {"items": [{"title": "nginx 502"}]}


def test_forbidden_maps_to_permission_error():
    tool = _tool(_client(lambda request: httpx.Response(403, text="Forbidden")), "audit.chain")

    with pytest.raises(ToolExecutionError) as excinfo:
        asyncio.run(tool.execute({}, _ctx()))

    assert excinfo.value.category is ToolErrorCategory.PERMISSION
    assert excinfo.value.retryable is False


def test_server_error_maps_to_retryable_network_error():
    tool = _tool(_client(lambda request: httpx.Response(503, text="unavailable")), "slo.status")

    with pytest.raises(ToolExecutionError) as excinfo:
        asyncio.run(tool.execute({}, _ctx()))

    assert excinfo.value.category is ToolErrorCategory.NETWORK
    assert excinfo.value.retryable is True


def test_user_session_headers_propagate_and_system_token_is_skipped():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": []})

    client = _client(handler, token="service-token")
    context = _ctx({"forwarded_headers": {"Cookie": "SESSION=abc", "X-Evil": "1"}})

    asyncio.run(_tool(client, "servers.list").execute({}, context))

    headers = {key.lower(): value for key, value in seen[0].headers.items()}
    assert headers["cookie"] == "SESSION=abc"
    assert "x-evil" not in headers
    assert "authorization" not in headers
    assert headers["x-agent-user-id"] == "u1"


def test_audit_chain_combines_backend_audit_and_local_verification():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/admin/audit"
        return httpx.Response(200, json={"data": {"items": [], "total": 0}})

    tool = _tool(
        _client(handler),
        "audit.chain",
        verify_audit_chain=lambda: {"ok": True, "segments": 1},
    )
    result = asyncio.run(tool.execute({}, _ctx()))

    assert result["source"] == "/api/admin/audit"
    assert result["local_chain"] == {"ok": True, "segments": 1}
