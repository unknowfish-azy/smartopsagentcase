"""MCP 工具目录单测：默认只读策略、显式 allowlist、字段映射。"""

from agent.mcp.catalog import CatalogEntry, ToolCatalog
from agent.policies.risk import RiskLevel
from agent.registry.tool_registry import ToolRegistry
from agent.sdk.tool import (
    ImplementationStatus,
    PluginTool,
    ToolDefinition,
)


class ReadTool(PluginTool):
    definition = ToolDefinition(
        name="demo.read",
        description="只读",
        risk=RiskLevel.LOW,
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "integer"}},
        },
    )

    async def execute(self, arguments, context):  # pragma: no cover
        return {}


class WriteTool(PluginTool):
    definition = ToolDefinition(
        name="demo.write",
        description="写操作",
        risk=RiskLevel.HIGH,
        idempotency="AT_MOST_ONCE",
    )

    async def execute(self, arguments, context):  # pragma: no cover
        return {}


class TemplateTool(PluginTool):
    definition = ToolDefinition(
        name="demo.template",
        description="模板",
        risk=RiskLevel.LOW,
        implementation_status=ImplementationStatus.TEMPLATE,
    )

    async def execute(self, arguments, context):  # pragma: no cover
        raise AssertionError("不应执行")


class LegacyTool:
    """没有 definition 的旧式工具。"""

    name = "demo.legacy"
    description = "旧式"
    risk_level = "LOW"
    requires_approval = False

    def execute(self, **kwargs):  # pragma: no cover
        return {}


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def test_default_policy_exposes_only_readonly_real_tools():
    catalog = ToolCatalog.from_registry(
        _registry(
            ReadTool(),
            WriteTool(),
            TemplateTool(),
        )
    )

    names = [entry.name for entry in catalog.list_entries()]

    assert names == ["demo.read"]
    assert len(catalog) == 1


def test_non_plugin_tool_is_ignored():
    """没有 `definition` 的旧式工具不得进入 MCP 暴露面。"""

    class _DuckRegistry:
        def __init__(self, tools):
            self._tools = tools

        def list(self):
            return list(self._tools)

    catalog = ToolCatalog.from_registry(
        _DuckRegistry([LegacyTool()])
    )

    assert len(catalog) == 0


def test_allowlist_overrides_default_policy():
    catalog = ToolCatalog.from_registry(
        _registry(ReadTool(), WriteTool()),
        allowlist=["demo.write"],
    )

    names = [entry.name for entry in catalog.list_entries()]

    assert names == ["demo.write"]


def test_allowlist_ignores_unknown_names():
    catalog = ToolCatalog.from_registry(
        _registry(ReadTool()),
        allowlist=["demo.read", "not.exist"],
    )

    names = [entry.name for entry in catalog.list_entries()]

    assert names == ["demo.read"]


def test_list_tools_shape():
    catalog = ToolCatalog.from_registry(_registry(ReadTool()))

    tools = catalog.list_tools()

    assert len(tools) == 1
    assert tools[0]["name"] == "demo.read"
    assert tools[0]["description"] == "只读"
    assert tools[0]["inputSchema"]["type"] == "object"


def test_missing_input_schema_defaults_to_empty_object():
    catalog = ToolCatalog.from_registry(
        _registry(WriteTool()),
        allowlist=["demo.write"],
    )

    entry = catalog.get("demo.write")

    assert entry is not None
    assert entry.input_schema == {}


def test_empty_catalog():
    catalog = ToolCatalog.empty()

    assert len(catalog) == 0
    assert catalog.list_tools() == []
    assert catalog.get("demo.read") is None


def test_entry_fields_are_mapped():
    catalog = ToolCatalog.from_registry(_registry(ReadTool()))
    entry = catalog.get("demo.read")

    assert isinstance(entry, CatalogEntry)
    assert entry.risk == RiskLevel.LOW
    assert entry.idempotency == "SAFE_RETRY"
    assert entry.implementation_status is ImplementationStatus.REAL
    assert isinstance(entry.tool, ReadTool)
