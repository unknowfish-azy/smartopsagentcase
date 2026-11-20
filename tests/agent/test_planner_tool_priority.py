"""DH-07 工具路由优先级测试：catalog 按 API > CLI > UI 排序，不可用标注，调用报错不自动降级。"""

from __future__ import annotations

import pytest

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.executor.models import ExecutionContext
from agent.planner.react_planner import ReActPlanner
from agent.policies.policy_engine import PolicyEngine
from agent.policies.risk import RiskLevel
from agent.sdk.model import ModelProvider, ModelResponse
from agent.sdk.tool import ImplementationStatus, PluginTool, ToolDefinition
from agent.tools.priority import (
    RouteTier,
    classify_tool,
    is_unavailable,
    sort_by_priority,
)
from agent.tools.registry import ToolRegistry


class _FakePlugin(PluginTool):
    def __init__(self, definition: ToolDefinition):
        self.definition = definition
        self.calls = 0

    async def execute(self, arguments, context):
        self.calls += 1
        return {"ok": True, "call": self.calls}


def _api_tool(name: str = "nn.anomaly", *, unavailable: bool = False) -> _FakePlugin:
    status = ImplementationStatus.UNAVAILABLE if unavailable else ImplementationStatus.REAL
    return _FakePlugin(
        ToolDefinition(
            name=name,
            description="API 感知工具",
            risk=RiskLevel.LOW,
            target_type="AI_SERVICE",
            implementation_status=status,
        )
    )


def _shell_tool(name: str = "shell.grep") -> _FakePlugin:
    return _FakePlugin(
        ToolDefinition(
            name=name,
            description="命令行搜索",
            risk=RiskLevel.LOW,
            target_type="REMOTE_HOST",
        )
    )


def _ui_tool(name: str = "desktop.observe") -> _FakePlugin:
    return _FakePlugin(
        ToolDefinition(
            name=name,
            description="桌面观测",
            risk=RiskLevel.LOW,
            target_type="DESKTOP",
        )
    )


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _planner(provider, registry):
    policy = ExecutionPolicy(max_retries=0, sleep_fn=lambda s: None)
    executor = AgentExecutor(registry, PolicyEngine(), execution_policy=policy)
    return ReActPlanner(provider, registry, executor)


def _context() -> ExecutionContext:
    return ExecutionContext("req-1", "user-1")


# ---------------------------------------------------------------------------
# 分类函数
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tool", "expected_tier"),
    [
        (_api_tool(), RouteTier.API),
        (_shell_tool(), RouteTier.SHELL),
        (_ui_tool(), RouteTier.UI),
    ],
)
def test_classify_tool_按_target_type_分组(tool, expected_tier):
    assert classify_tool(tool) == expected_tier


def test_classify_tool_按名字前缀_回退():
    # 旧式工具没有 definition，按名字前缀猜
    class _OldTool:
        def __init__(self, name):
            self.name = name

    assert classify_tool(_OldTool("nn.logclassify")) == RouteTier.API
    assert classify_tool(_OldTool("shell.ps")) == RouteTier.SHELL
    assert classify_tool(_OldTool("desktop.click")) == RouteTier.UI
    assert classify_tool(_OldTool("something.else")) == RouteTier.UNKNOWN


def test_unavailable_基于_definition_implementation_status():
    assert is_unavailable(_api_tool(unavailable=False)) is False
    assert is_unavailable(_api_tool(unavailable=True)) is True
    # 旧式工具没有 definition，默认可用（避免误杀）
    class _OldTool:
        name = "x"
    assert is_unavailable(_OldTool()) is False


# ---------------------------------------------------------------------------
# catalog 排序
# ---------------------------------------------------------------------------


def test_catalog_三者在场时_API_排在最前():
    api = _api_tool()
    shell = _shell_tool()
    ui = _ui_tool()
    planner = _planner(_NoopProvider(), _registry(ui, shell, api))  # 故意乱序注册

    catalog = planner._build_catalog()

    api_pos = catalog.index("### API")
    shell_pos = catalog.index("### CLI")
    ui_pos = catalog.index("### UI")
    assert api_pos < shell_pos < ui_pos


def test_catalog_只存在_shell_和_ui_时_shell_在前():
    shell = _shell_tool()
    ui = _ui_tool()
    planner = _planner(_NoopProvider(), _registry(ui, shell))

    catalog = planner._build_catalog()

    assert catalog.index("### CLI") < catalog.index("### UI")


def test_catalog_不可用工具标注_但仍留在本组():
    api_ok = _api_tool(name="nn.logclassify")
    api_down = _api_tool(name="nn.anomaly", unavailable=True)
    planner = _planner(_NoopProvider(), _registry(api_down, api_ok))

    catalog = planner._build_catalog()

    assert "(不可用)" in catalog
    assert "nn.anomaly (不可用)" in catalog
    assert "### API" in catalog
    assert "### CLI" not in catalog  # 没有 shell 工具就不出现


def test_catalog_按组标题分隔_LLM_一眼能分清楚():
    planner = _planner(_NoopProvider(), _registry(_api_tool(), _shell_tool(), _ui_tool()))

    catalog = planner._build_catalog()

    sections = [line for line in catalog.splitlines() if line.startswith("### ")]
    assert sections == [
        "### API（优先）",
        "### CLI（次选）",
        "### UI（兜底，仅在前两者明确不可用时）",
    ]


# ---------------------------------------------------------------------------
# 系统提示词明确写优先级
# ---------------------------------------------------------------------------


def test_system_prompt_明确写_API_优先_规则():
    from agent.planner.react_planner import REACT_SYSTEM_PROMPT

    assert "API" in REACT_SYSTEM_PROMPT
    assert "shell" in REACT_SYSTEM_PROMPT.lower()
    assert "desktop" in REACT_SYSTEM_PROMPT.lower()
    assert "调用报错" in REACT_SYSTEM_PROMPT
    assert "明确不可用" in REACT_SYSTEM_PROMPT
    assert "sort_by_priority" not in REACT_SYSTEM_PROMPT  # 内部实现不应泄漏到 prompt


# ---------------------------------------------------------------------------
# 调用报错不自动降级（核心：planner 没有自动路由逻辑）
# ---------------------------------------------------------------------------


class _ErroringAPI(PluginTool):
    """每次调用都报错的 API 工具（模拟偶发超时）。"""

    def __init__(self):
        self.definition = ToolDefinition(
            name="nn.anomaly",
            description="总是报错",
            risk=RiskLevel.LOW,
            target_type="AI_SERVICE",
        )
        self.calls = 0

    async def execute(self, arguments, context):
        self.calls += 1
        raise RuntimeError("连接超时")


class _DesktopCounter(PluginTool):
    def __init__(self):
        self.calls = 0
        self.definition = ToolDefinition(
            name="desktop.observe", description="桌面观测", target_type="DESKTOP"
        )

    async def execute(self, arguments, context):
        self.calls += 1
        return {"ok": True}


class _AlwaysFinal(ModelProvider):
    """按脚本依次返回 Action / Final Answer——脚本项就是完整的 response content。"""

    def __init__(self, plan):
        self.plan = list(plan)
        self.prompts = []

    @property
    def name(self):
        return "always-final"

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        if self.plan:
            item = self.plan.pop(0)
            return ModelResponse(content=item, model="p", provider="p", metadata={})
        return ModelResponse(
            content="Final Answer: 完", model="p", provider="p", metadata={}
        )


def test_planner_不做自动降级_LLM_选了_API_报错_不会自动切_desktop():
    api = _ErroringAPI()
    desktop = _DesktopCounter()
    plan = [
        "Thought: 先试 API\n"
        "Action: nn.anomaly\n"
        "Action Input: {}\n",
        "Thought: 再试一次 API\n"
        "Action: nn.anomaly\n"
        "Action Input: {}\n",
    ]
    planner = _planner(_AlwaysFinal(plan), _registry(api, desktop))

    result = planner.run("排查问题", _context())

    # API 工具被调了两次，桌面工具一次都没被调用
    assert api.calls == 2
    assert desktop.calls == 0
    # planner 没有自动路由——两次都是 LLM 自己选的 nn.anomaly
    trajectory = result.trajectory
    api_actions = [step for step in trajectory if step.action == "nn.anomaly"]
    desktop_actions = [step for step in trajectory if step.action == "desktop.observe"]
    assert len(api_actions) == 2
    assert len(desktop_actions) == 0
    # 第二次报错的 Observation 里应该包含"连接超时"（让 LLM 自己决定要不要换）
    assert "连接超时" in api_actions[-1].observation


def test_sort_by_priority_同_tier_内_可用在前_不可用在后():
    ok = _api_tool(name="nn.anomaly")
    down = _api_tool(name="nn.logclassify", unavailable=True)

    sorted_tools = sort_by_priority([down, ok])

    assert [t.name for t in sorted_tools] == ["nn.anomaly", "nn.logclassify"]


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------


class _NoopProvider(ModelProvider):
    """只用于 catalog 测试：从不被调用。"""

    @property
    def name(self):
        return "noop"

    async def generate(self, prompt, **kwargs):
        raise AssertionError("不应被调用")
