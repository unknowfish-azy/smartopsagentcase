"""Z0-01：Tool 契约一致性守卫。

目的不是测功能，而是保证"四批任务不会各自长出一套工具基类"。

实测基线（2026-11-20）：
- `agent/tools/base.py::AgentTool` 是旧式契约（类属性 + `execute(**kwargs)`）；
- `agent/sdk/tool.py::PluginTool` 是新式契约（`ToolDefinition` + `async execute(args, ctx)`）；
- 两种写法由 executor 的适配层兼容，所以守卫只断言**对外可见字段**一致：
  `name` / `risk_level` / `requires_approval` / `execute` / `definition.input_schema`。
"""

from __future__ import annotations

import pytest

from agent.policies.risk import RiskLevel

from agent.tools.builtin.nn_perception import build_nn_perception_tools
from agent.tools.desktop import build_desktop_tools

VALID_RISK = {RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL}
#: 语义上必须人工审批的风险档
APPROVAL_REQUIRED_RISK = {RiskLevel.HIGH, RiskLevel.CRITICAL}


def _desktop_tools():
    # enabled=False：默认姿态，仍会构造 definition，无需真实 driver
    return build_desktop_tools(object(), enabled=False)


def _all_tools():
    return list(build_nn_perception_tools(base_url="http://127.0.0.1:8001")) + _desktop_tools()


def test_every_tool_declares_full_contract():
    tools = _all_tools()
    assert tools, "工具集为空，守卫失效"

    for tool in tools:
        assert isinstance(tool.name, str) and tool.name, f"{tool!r} 缺 name"
        assert "." in tool.name, f"{tool.name} 必须带命名空间前缀"

        risk = RiskLevel(tool.risk_level)
        assert risk in VALID_RISK, f"{tool.name} 的 risk_level 非法：{tool.risk_level!r}"

        assert isinstance(tool.requires_approval, bool), f"{tool.name} 的 requires_approval 必须是 bool"

        assert callable(tool.execute), f"{tool.name} 缺可调用的 execute"

        definition = getattr(tool, "definition", None)
        assert definition is not None, f"{tool.name} 缺 definition"
        assert definition.name == tool.name, f"{tool.name} 的 definition.name 不一致"
        assert isinstance(definition.input_schema, dict), f"{tool.name} 的 input_schema 必须是 dict"


def test_tool_names_are_globally_unique():
    names = [tool.name for tool in _all_tools()]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert duplicates == [], f"工具名重复：{duplicates}"


def test_high_risk_tools_require_approval():
    for tool in _all_tools():
        if RiskLevel(tool.risk_level) in APPROVAL_REQUIRED_RISK:
            assert tool.requires_approval is True, f"{tool.name} 是高风险却没有 requires_approval"


def test_desktop_click_schema_has_no_coordinates():
    """桌面手铁律 3：LLM 只能给 element_id，永不给坐标。"""
    click = next(t for t in _desktop_tools() if t.name == "desktop.click")
    properties = set(click.definition.input_schema.get("properties", {}))
    assert properties & {"x", "y", "coord", "coords", "position"} == set()
    assert "element_id" in properties


def test_desktop_resume_is_not_registered():
    """急停恢复只能由人做，Agent 侧不得存在该工具（ARCHITECTURE §9）。"""
    with pytest.raises(StopIteration):
        next(t for t in _desktop_tools() if t.name == "desktop.resume")
