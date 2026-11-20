"""DH-05 工具面测试：六个工具的形状、门禁接线与"不暴露坐标 / 不暴露 resume"。

全部用 FakeDriver：不碰系统 API，也不依赖 Windows。
"""

from __future__ import annotations

import pytest

from agent.desktop.driver_fake import FakeDriver
from agent.desktop.element_id import element_id
from agent.desktop.gateway import DesktopGateway
from agent.desktop.models import UiElement, WindowInfo
from agent.desktop.policy import DesktopPolicy, WindowRule
from agent.policies.risk import RiskLevel
from agent.tools.errors import ToolExecutionError
from agent.tools.registry import ToolRegistry
from agent.tools.validation import validate_arguments
from agent.tools.desktop import DesktopHand, build_desktop_tools

EXPECTED_TOOLS = {
    "desktop.observe": (RiskLevel.LOW, False),
    "desktop.focus_window": (RiskLevel.MEDIUM, False),
    "desktop.click": (RiskLevel.HIGH, True),
    "desktop.type": (RiskLevel.HIGH, True),
    "desktop.key": (RiskLevel.HIGH, True),
    "desktop.status": (RiskLevel.LOW, False),
}


def _element(name: str = "保存", role: str = "button") -> UiElement:
    bbox = (0, 0, 100, 30)
    return UiElement(
        element_id=element_id("hwnd-1", role, name, bbox),
        role=role,
        name=name,
        bbox=bbox,
    )


def _policy(*, input_group_enabled: bool = False) -> DesktopPolicy:
    return DesktopPolicy(
        input_group_enabled=input_group_enabled,
        window_allowlist=(
            WindowRule(
                process="notepad.exe",
                title_regex=".*",
                allowed_roles=frozenset({"button", "edit"}),
            ),
        ),
    )


def _hand(
    *,
    elements: list[UiElement] | None = None,
    policy: DesktopPolicy | None = None,
    process: str = "notepad.exe",
    title: str = "记事本",
) -> tuple[DesktopHand, FakeDriver]:
    window = WindowInfo("hwnd-1", title, process)
    driver = FakeDriver(
        windows=[window],
        elements={"hwnd-1": list(elements or [_element()])},
    )
    gateway = DesktopGateway(policy if policy is not None else _policy())
    return DesktopHand(driver, gateway), driver


def _tool(hand: DesktopHand, name: str):
    return {tool.name: tool for tool in build_desktop_tools(hand)}[name]


# ---------------------------------------------------------------------------
# 工具形状
# ---------------------------------------------------------------------------


def test_六个工具字段齐全():
    hand, _ = _hand()

    tools = {tool.name: tool for tool in build_desktop_tools(hand)}

    assert set(tools) == set(EXPECTED_TOOLS)
    for name, (risk, approval) in EXPECTED_TOOLS.items():
        tool = tools[name]
        assert tool.description, f"{name} 缺少 description"
        assert tool.risk_level == risk
        assert tool.requires_approval is approval
        assert tool.definition.name == name
        assert tool.definition.risk == risk
        assert tool.definition.input_schema["type"] == "object"


def _all_property_names(schema: dict) -> set[str]:
    names: set[str] = set()
    for key, rule in schema.get("properties", {}).items():
        names.add(key)
        names |= _all_property_names(rule)
    return names


@pytest.mark.parametrize("tool_name", ["desktop.click", "desktop.type", "desktop.key"])
def test_输入类工具_schema_不含坐标(tool_name):
    hand, _ = _hand()

    schema = _tool(hand, tool_name).definition.input_schema

    assert _all_property_names(schema).isdisjoint({"x", "y", "coord", "coordinate", "coordinates"})


def test_click_传入坐标会被参数校验拒绝():
    hand, _ = _hand()
    schema = _tool(hand, "desktop.click").definition.input_schema

    with pytest.raises(ToolExecutionError):
        validate_arguments(
            schema, {"window_id": "hwnd-1", "element_id": "e" * 16, "x": 10}
        )


def test_注册表没有_resume_也没有坐标点击():
    hand, _ = _hand()
    registry = ToolRegistry()

    registry.register_desktop_tools(hand)

    names = {tool.name for tool in registry.list_tools()}
    assert names == set(EXPECTED_TOOLS)
    assert registry.get("desktop.resume") is None
    assert registry.get("desktop.coordinate_click") is None


# ---------------------------------------------------------------------------
# 只读能力
# ---------------------------------------------------------------------------


def test_observe_返回元素树且不含图片字节():
    hand, _ = _hand()

    result = _tool(hand, "desktop.observe").execute(window_id="hwnd-1")

    assert result["ok"] is True
    assert result["shot_digest"].startswith("sha256:")
    assert "image" not in result and "image_b64" not in result
    assert result["elements"][0]["name"] == "保存"
    assert result["elements"][0]["bbox"] == [0, 0, 100, 30]


def test_status_报告驱动与输入组开关():
    hand, _ = _hand(policy=_policy(input_group_enabled=False))

    result = _tool(hand, "desktop.status").execute()

    assert result["ok"] is True
    assert result["driver"]["available"] is True
    assert result["driver"]["name"] == "fake"
    assert result["gateway"]["input_group_enabled"] is False


def test_未知窗口返回结构化错误而不抛异常():
    hand, _ = _hand()

    result = _tool(hand, "desktop.observe").execute(window_id="hwnd-404")

    assert result["ok"] is False
    assert "窗口不存在" in result["error"]


# ---------------------------------------------------------------------------
# 门禁接线：工具层不得自己做策略判断
# ---------------------------------------------------------------------------


def test_输入组默认关闭时_click_被明确拒绝():
    hand, driver = _hand(policy=_policy(input_group_enabled=False))

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=_element().element_id
    )

    assert result["ok"] is False
    assert result["reject_reason"] == "INPUT_GROUP_DISABLED"
    assert "输入组" in result["message"]
    # 拒绝后绝不能再落到 driver.click
    assert [name for name, _ in driver.calls] == ["observe"]


def test_输入组开启且白名单命中时_click_放行():
    hand, driver = _hand(policy=_policy(input_group_enabled=True))
    target = _element().element_id

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=target
    )

    assert result["ok"] is True
    assert result["before_shot_digest"].startswith("sha256:")
    assert ("click", {"window_id": "hwnd-1", "element_id": target}) in driver.calls


def test_危险文案元素被_R1_拒绝():
    hand, driver = _hand(
        elements=[_element(name="确认支付")],
        policy=_policy(input_group_enabled=True),
    )

    result = _tool(hand, "desktop.click").execute(
        window_id="hwnd-1", element_id=_element(name="确认支付").element_id
    )

    assert result["reject_reason"] == "R1_DESTRUCTIVE_ELEMENT"
    assert "代签" in result["message"]
    assert [name for name, _ in driver.calls] == ["observe"]


def test_禁入进程窗口被_R2_拒绝():
    hand, _ = _hand(process="cmd.exe")

    result = _tool(hand, "desktop.observe").execute(window_id="hwnd-1")

    assert result["reject_reason"] == "R2_FORBIDDEN_PROCESS"


def test_非白名单窗口被_R3_拒绝():
    hand, _ = _hand(process="other.exe")

    result = _tool(hand, "desktop.observe").execute(window_id="hwnd-1")

    assert result["reject_reason"] == "R3_WINDOW_NOT_ALLOWED"


def test_白名单外的按键被_R2_拒绝():
    hand, driver = _hand(policy=_policy(input_group_enabled=True))

    result = _tool(hand, "desktop.key").execute(window_id="hwnd-1", key="win+r")

    assert result["reject_reason"] == "R2_FORBIDDEN_KEY"
    assert [name for name, _ in driver.calls] == ["observe"]


def test_type_把文本交给驱动():
    hand, driver = _hand(elements=[_element(name="输入框", role="edit")], policy=_policy(input_group_enabled=True))
    target = _element(name="输入框", role="edit").element_id

    result = _tool(hand, "desktop.type").execute(
        window_id="hwnd-1", element_id=target, text="巡检正常"
    )

    assert result["ok"] is True
    assert result["chars"] == 4
    assert ("type", {"window_id": "hwnd-1", "element_id": target, "text": "巡检正常"}) in driver.calls


def test_focus_window_前后各观测一次并产出回执():
    hand, driver = _hand()

    result = _tool(hand, "desktop.focus_window").execute(window_id="hwnd-1")

    assert result["ok"] is True
    assert [name for name, _ in driver.calls] == ["observe", "focus_window", "observe"]
    assert result["receipt"]["action"] == "focus_window"
    assert result["receipt"]["after_shot_digest"] is not None
