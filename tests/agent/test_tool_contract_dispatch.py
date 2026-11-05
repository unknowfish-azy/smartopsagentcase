"""OPS-01：Python 与 Java 工具语义必须一致，异步插件工具不能再"注册了但调不动"。"""

from agent.executor.executor import AgentExecutor
from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep
from agent.policies.policy_engine import PolicyEngine
from agent.policies.risk import RiskLevel
from agent.sdk.tool import ImplementationStatus, PluginTool, ToolDefinition
from agent.tools.registry import ToolRegistry


class AsyncPlugin(PluginTool):
    definition = ToolDefinition(name="docker.ps", description="列出容器", risk=RiskLevel.LOW)

    def __init__(self):
        self.received = None

    async def execute(self, arguments, context):
        self.received = (arguments, context)
        return {"containers": []}


class TemplateOnlyTool(PluginTool):
    definition = ToolDefinition(
        name="db.inspect",
        description="只读巡检（仅有模板）",
        risk=RiskLevel.LOW,
        implementation_status=ImplementationStatus.TEMPLATE,
    )

    async def execute(self, arguments, context):  # pragma: no cover - 不应被调用
        raise AssertionError("TEMPLATE 工具不允许执行")


def _execute(tool, arguments):
    registry = ToolRegistry()
    registry.register(tool)
    executor = AgentExecutor(registry, PolicyEngine())
    step = PlanStep(1, "执行", tool.definition.name, arguments)
    return executor.execute(step, ExecutionContext("request-1", "user-1"))


def test_async_plugin_uses_arguments_and_context_contract():
    tool = AsyncPlugin()
    result = _execute(tool, {"all": True})

    assert result.success is True
    assert tool.received is not None
    assert tool.received[0] == {"all": True}
    assert isinstance(tool.received[1], ExecutionContext)


def test_template_tool_is_rejected_before_execution():
    result = _execute(TemplateOnlyTool(), {"metric": "cpu"})

    assert result.success is False
    assert result.error is not None and "TOOL_IMPLEMENTATION_UNAVAILABLE" in result.error
