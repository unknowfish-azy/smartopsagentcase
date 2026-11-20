"""DH-08 默认关与环境变量集成测试。

核心判据：DESKTOP_HAND_ENABLED 未设 / 为 false → 所有 desktop.* 工具
definition.implementation_status == UNAVAILABLE → catalog 标 "(不可用)"。
"""

from __future__ import annotations

import pytest

from agent.desktop.driver_fake import FakeDriver
from agent.desktop.gateway import DesktopGateway
from agent.desktop.models import WindowInfo
from agent.desktop.policy import (
    DesktopPolicy,
    WindowRule,
    desktop_hand_enabled,
)
from agent.planner.react_planner import ReActPlanner
from agent.sdk.model import ModelProvider, ModelResponse
from agent.sdk.tool import ImplementationStatus, PluginTool, ToolDefinition
from agent.tools.desktop import DesktopHand, build_desktop_tools
from agent.tools.priority import is_unavailable
from agent.tools.registry import ToolRegistry


class _NoopProvider(ModelProvider):
    @property
    def name(self):
        return "noop"

    async def generate(self, prompt, **kwargs):
        raise AssertionError("不应被调用")


def _hand(*, input_group_enabled: bool = True, enabled: bool = True) -> DesktopHand:
    driver = FakeDriver(
        windows=[WindowInfo("hwnd-1", "记事本", "notepad.exe")],
        elements={"hwnd-1": []},
    )
    policy = DesktopPolicy(
        input_group_enabled=input_group_enabled,
        window_allowlist=(
            WindowRule("notepad.exe", ".*", allowed_roles=frozenset({"button"})),
        ),
    )
    return DesktopHand(driver, DesktopGateway(policy, enabled=enabled))


# ---------------------------------------------------------------------------
# 环境变量默认值
# ---------------------------------------------------------------------------


def test_desktop_hand_enabled_默认_false(monkeypatch):
    monkeypatch.delenv("DESKTOP_HAND_ENABLED", raising=False)
    monkeypatch.delenv("SMARTOPS_DESKTOP_HAND_ENABLED", raising=False)

    assert desktop_hand_enabled() is False


def test_desktop_hand_enabled_显式_true(monkeypatch):
    monkeypatch.setenv("DESKTOP_HAND_ENABLED", "true")

    assert desktop_hand_enabled() is True


def test_smartops_前缀_fallback(monkeypatch):
    monkeypatch.delenv("DESKTOP_HAND_ENABLED", raising=False)
    monkeypatch.setenv("SMARTOPS_DESKTOP_HAND_ENABLED", "1")

    assert desktop_hand_enabled() is True


def test_desktop_policy_from_env_默认输入组关(monkeypatch):
    monkeypatch.delenv("DESKTOP_HAND_INPUT_GROUP", raising=False)
    monkeypatch.delenv("SMARTOPS_DESKTOP_HAND_INPUT_GROUP", raising=False)

    policy = DesktopPolicy.from_env()
    assert policy.input_group_enabled is False


# ---------------------------------------------------------------------------
# 总开关关 → 工具标 UNAVAILABLE
# ---------------------------------------------------------------------------


def test_build_desktop_tools_enabled_false_implementation_status_为_unavailable():
    hand = _hand()

    disabled_tools = build_desktop_tools(hand, enabled=False)
    enabled_tools = build_desktop_tools(hand, enabled=True)

    for tool in disabled_tools:
        assert tool.definition.implementation_status == ImplementationStatus.UNAVAILABLE
        assert is_unavailable(tool) is True

    for tool in enabled_tools:
        assert tool.definition.implementation_status == ImplementationStatus.REAL
        assert is_unavailable(tool) is False


def test_catalog_把_unavailable_desktop_标_不可用():
    registry = ToolRegistry()
    registry.register_desktop_tools(_hand(), enabled=False)

    planner = ReActPlanner(_NoopProvider(), registry, None)

    catalog = planner._build_catalog()
    assert "(不可用)" in catalog
    assert "### UI" in catalog
    assert "desktop.observe (不可用)" in catalog
    assert "desktop.click (不可用)" in catalog


def test_registry_register_desktop_tools_默认读环境变量_false(monkeypatch):
    monkeypatch.delenv("DESKTOP_HAND_ENABLED", raising=False)
    monkeypatch.delenv("SMARTOPS_DESKTOP_HAND_ENABLED", raising=False)

    registry = ToolRegistry()
    registry.register_desktop_tools(_hand())  # enabled=None 走默认

    for tool in registry.list_tools():
        assert tool.definition.implementation_status == ImplementationStatus.UNAVAILABLE


# ---------------------------------------------------------------------------
# 总开关关 → gateway TOTAL_DISABLED
# ---------------------------------------------------------------------------


def test_gateway总开关关时_authorize_返回_TOTAL_DISABLED():
    gate = DesktopGateway(enabled=False)

    decision = gate.authorize("observe", {"window_id": "hwnd-1"})

    assert decision.allowed is False
    assert decision.reject_reason == "TOTAL_DISABLED"


def test_desktop_hand_observe_在总开关关时返回_rejected():
    hand = _hand(enabled=False)

    result = hand.observe("hwnd-1")

    assert result["ok"] is False
    assert result["reject_reason"] == "TOTAL_DISABLED"
    assert result["receipt"]["verdict"] == "REJECTED"
