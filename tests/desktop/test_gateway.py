"""DH-02：六道门禁（ARCHITECTURE H1–H6、H9）。"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from agent.desktop.element_id import element_id
from agent.desktop.gateway import DesktopGateway
from agent.desktop.models import DesktopContractError, UiElement, UiObservation
from agent.desktop.policy import (
    DESTRUCTIVE_TEXT,
    FORBIDDEN_PROCESSES,
    DesktopPolicy,
    WindowRule,
)

DIGEST = "sha256:" + "0" * 64
WINDOW = "w-notepad-1"


def make_element(
    role: str = "button",
    name: str = "保存",
    bbox: tuple[int, int, int, int] = (10, 10, 80, 30),
    *,
    enabled: bool = True,
    window_id: str = WINDOW,
) -> UiElement:
    return UiElement(
        element_id=element_id(window_id, role, name, bbox),
        role=role,
        name=name,
        bbox=bbox,
        enabled=enabled,
    )


def make_obs(
    *elements: UiElement,
    truncated: bool = False,
    process: str = "notepad.exe",
    title: str = "无标题 - 记事本",
    window_id: str = WINDOW,
) -> UiObservation:
    return UiObservation(
        window_id=window_id,
        window_title=title,
        process_name=process,
        shot_digest=DIGEST,
        captured_at=datetime.now(timezone.utc),
        elements=list(elements),
        truncated=truncated,
    )


def make_policy(
    *,
    input_group: bool = True,
    process: str = "notepad.exe",
    title: str = r".*记事本.*",
    roles: tuple[str, ...] = ("button", "edit"),
    budget: int = 50,
    interval: int = 0,
    streak: int = 3,
    allowlist: tuple[WindowRule, ...] | None = None,
) -> DesktopPolicy:
    rules = allowlist
    if rules is None:
        rules = (
            WindowRule(
                process=process,
                title_regex=title,
                allowed_roles=frozenset(roles),
            ),
        )
    return DesktopPolicy(
        input_group_enabled=input_group,
        window_allowlist=rules,
        step_budget=budget,
        min_interval_ms=interval,
        same_element_streak_limit=streak,
    )


def click(gateway: DesktopGateway, obs: UiObservation, element: UiElement, **kwargs):
    return gateway.authorize(
        "click",
        {"window_id": obs.window_id, "element_id": element.element_id},
        obs,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 默认姿态
# ---------------------------------------------------------------------------

def test_default_policy_is_fail_closed():
    policy = DesktopPolicy()

    assert policy.input_group_enabled is False
    assert policy.window_allowlist == ()
    assert policy.step_budget == 50
    assert policy.min_interval_ms == 300
    assert policy.same_element_streak_limit == 3


def test_r1_r2_have_no_config_switch():
    field_names = {item.name for item in dataclasses.fields(DesktopPolicy)}

    assert not any(
        keyword in name
        for name in field_names
        for keyword in ("disable", "forbidden", "destructive", "allow_dangerous")
    )
    assert "cmd" in FORBIDDEN_PROCESSES
    assert "确认" in DESTRUCTIVE_TEXT


def test_empty_allowlist_rejects_everything():
    gateway = DesktopGateway(DesktopPolicy(input_group_enabled=True))
    obs = make_obs(make_element())

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "R3_WINDOW_NOT_ALLOWED"


# ---------------------------------------------------------------------------
# H1 输入组默认关闭
# ---------------------------------------------------------------------------

def test_h1_input_group_disabled_rejects_click():
    gateway = DesktopGateway(make_policy(input_group=False))
    obs = make_obs(make_element())

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "INPUT_GROUP_DISABLED"


def test_h1_input_group_enabled_allows_click_with_approval():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is True
    assert decision.needs_approval is True


def test_observe_is_available_while_input_group_is_disabled():
    gateway = DesktopGateway(make_policy(input_group=False))
    obs = make_obs(make_element())

    decision = gateway.authorize("observe", {"window_id": WINDOW}, obs)

    assert decision.allowed is True
    assert decision.needs_approval is False


# ---------------------------------------------------------------------------
# H2 R1 代签
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "label",
    ["确认支付", "同意并继续", "确定", "授权访问", "签署协议", "Delete", "CONFIRM"],
)
def test_h2_destructive_element_is_rejected(label):
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element(name=label))

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "R1_DESTRUCTIVE_ELEMENT"


def test_h2_model_flag_is_respected():
    element = UiElement(
        element_id=element_id(WINDOW, "button", "下一步", (1, 1, 2, 2)),
        role="button",
        name="下一步",
        bbox=(1, 1, 2, 2),
        is_destructive=True,
    )
    gateway = DesktopGateway(make_policy(input_group=True))

    decision = click(gateway, make_obs(element), element)

    assert decision.reject_reason == "R1_DESTRUCTIVE_ELEMENT"


# ---------------------------------------------------------------------------
# H3 R2 禁入区
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "process",
    ["cmd.exe", "C:\\Windows\\System32\\powershell.exe", "regedit.exe", "taskmgr.exe"],
)
def test_h3_forbidden_process_is_rejected(process):
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element(), process=process)

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "R2_FORBIDDEN_PROCESS"


def test_h3_forbidden_window_title_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element(), title="注册表编辑器")

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "R2_FORBIDDEN_WINDOW"


@pytest.mark.parametrize("key", ["win+r", "meta", "alt+f4", "ctrl+shift+escape"])
def test_h3_escape_keys_are_rejected(key):
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())

    decision = gateway.authorize("key", {"window_id": WINDOW}, obs, key=key)

    assert decision.allowed is False
    assert decision.reject_reason == "R2_FORBIDDEN_KEY"


@pytest.mark.parametrize("key", ["Ctrl+V", "ctrl+w"])
def test_allowed_key_passes(key):
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())

    decision = gateway.authorize("key", {"window_id": WINDOW}, obs, key=key)

    assert decision.allowed is True


# ---------------------------------------------------------------------------
# H4 R3 窗口白名单
# ---------------------------------------------------------------------------

def test_h4_window_not_in_allowlist_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element(), process="chrome.exe", title="某后台 - Chrome")

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "R3_WINDOW_NOT_ALLOWED"


def test_h4_title_regex_must_match():
    gateway = DesktopGateway(make_policy(input_group=True, title=r"^生产系统"))
    obs = make_obs(make_element())

    decision = click(gateway, obs, obs.elements[0])

    assert decision.reject_reason == "R3_WINDOW_NOT_ALLOWED"


def test_h4_role_not_allowed_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True, roles=("button",)))
    obs = make_obs(make_element(role="menuitem", name="文件"))

    decision = click(gateway, obs, obs.elements[0])

    assert decision.allowed is False
    assert decision.reject_reason == "R3_ROLE_NOT_ALLOWED"


def test_h4_focus_window_allowed_without_role():
    gateway = DesktopGateway(make_policy(input_group=True, roles=()))
    obs = make_obs(make_element())

    assert gateway.authorize("focus_window", {"window_id": WINDOW}, obs).allowed is True


def test_no_window_information_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True))

    decision = gateway.authorize("observe", {"window_id": WINDOW})

    assert decision.allowed is False
    assert decision.reject_reason == "R3_NO_WINDOW"


# ---------------------------------------------------------------------------
# H5 R4 预算 / 限速 / 重复点击
# ---------------------------------------------------------------------------

def test_h5_step_budget_blocks_51st_action():
    gateway = DesktopGateway(make_policy(input_group=True, budget=50))
    elements = [
        make_element(bbox=(index, index, index + 10, index + 10)) for index in range(60)
    ]
    obs = make_obs(*elements)

    decisions = [click(gateway, obs, element) for element in elements[:50]]
    assert all(decision.allowed for decision in decisions)

    blocked = click(gateway, obs, elements[50])
    assert blocked.allowed is False
    assert blocked.reject_reason == "R4_BUDGET"


def test_h5_same_element_fourth_click_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True, streak=3))
    element = make_element()
    obs = make_obs(element)

    assert [click(gateway, obs, element).allowed for _ in range(3)] == [True] * 3

    blocked = click(gateway, obs, element)
    assert blocked.allowed is False
    assert blocked.reject_reason == "R4_REPEAT"


def test_h5_rate_limit_rejects_too_fast_action():
    gateway = DesktopGateway(make_policy(input_group=True, interval=300))
    obs = make_obs(make_element(bbox=(0, 0, 1, 1)), make_element(bbox=(2, 2, 3, 3)))

    assert click(gateway, obs, obs.elements[0], now=0.0).allowed is True

    too_fast = click(gateway, obs, obs.elements[1], now=0.1)
    assert too_fast.allowed is False
    assert too_fast.reject_reason == "R4_RATE"

    assert click(gateway, obs, obs.elements[1], now=0.4).allowed is True


# ---------------------------------------------------------------------------
# H6 R5 急停
# ---------------------------------------------------------------------------

def test_h6_emergency_stop_blocks_every_action():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())
    token = gateway.emergency_stop("operator pressed hotkey")
    assert token

    assert gateway.authorize("observe", {"window_id": WINDOW}, obs).reject_reason == "R5_STOPPED"
    assert click(gateway, obs, obs.elements[0]).reject_reason == "R5_STOPPED"


def test_h6_agent_cannot_resume():
    gateway = DesktopGateway(make_policy(input_group=True))
    gateway.emergency_stop("test")

    assert gateway.resume().reject_reason == "R5_AGENT_CANNOT_RESUME"
    assert gateway.resume("").reject_reason == "R5_AGENT_CANNOT_RESUME"
    assert gateway.resume("guess").reject_reason == "R5_AGENT_CANNOT_RESUME"
    assert gateway.status()["stopped"] is True


def test_h6_human_token_resumes():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())
    token = gateway.emergency_stop("test")

    assert gateway.resume(token).allowed is True
    assert gateway.status()["stopped"] is False
    assert click(gateway, obs, obs.elements[0]).allowed is True


def test_resume_when_not_stopped_is_noop():
    gateway = DesktopGateway(make_policy(input_group=True))
    assert gateway.resume().allowed is True


# ---------------------------------------------------------------------------
# H9 R6 截断观测
# ---------------------------------------------------------------------------

def test_h9_truncated_observation_blocks_click_and_type():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element(), make_element(bbox=(1, 1, 2, 2)), truncated=True)
    element = obs.elements[0]

    assert click(gateway, obs, element).reject_reason == "R6_TRUNCATED"
    assert (
        gateway.authorize(
            "type",
            {"window_id": WINDOW, "element_id": element.element_id},
            obs,
        ).reject_reason
        == "R6_TRUNCATED"
    )


def test_missing_observation_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True))

    decision = gateway.authorize(
        "click",
        {"window_id": WINDOW, "element_id": "0123456789abcdef"},
    )

    assert decision.reject_reason == "R6_NO_OBSERVATION"


def test_stale_element_id_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())

    decision = gateway.authorize(
        "click",
        {"window_id": WINDOW, "element_id": "ffffffffffffffff"},
        obs,
    )

    assert decision.reject_reason == "R6_ELEMENT_UNKNOWN"


def test_observation_of_other_window_is_rejected():
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())

    decision = gateway.authorize(
        "click",
        {"window_id": "w-other", "element_id": obs.elements[0].element_id},
        obs,
        window=obs.as_window(),
    )

    assert decision.reject_reason == "R6_WINDOW_MISMATCH"


# ---------------------------------------------------------------------------
# 顺序固定 / 坐标禁止
# ---------------------------------------------------------------------------

def test_check_order_truncated_wins_over_destructive_and_input_group():
    gateway = DesktopGateway(make_policy(input_group=False))
    obs = make_obs(
        make_element(name="确认支付"),
        make_element(name="取消", bbox=(1, 1, 2, 2)),
        truncated=True,
    )

    assert click(gateway, obs, obs.elements[0]).reject_reason == "R6_TRUNCATED"


def test_check_order_forbidden_process_wins_over_destructive():
    gateway = DesktopGateway(make_policy(input_group=False))
    obs = make_obs(make_element(name="确认支付"), process="cmd.exe")

    assert click(gateway, obs, obs.elements[0]).reject_reason == "R2_FORBIDDEN_PROCESS"


@pytest.mark.parametrize("extra", [{"x": 100}, {"y": 200}, {"coord": (1, 2)}])
def test_coordinate_target_is_a_contract_error(extra):
    gateway = DesktopGateway(make_policy(input_group=True))
    obs = make_obs(make_element())

    with pytest.raises(DesktopContractError):
        gateway.authorize(
            "click",
            {"window_id": WINDOW, "element_id": obs.elements[0].element_id, **extra},
            obs,
        )


def test_unknown_action_is_a_contract_error():
    gateway = DesktopGateway(make_policy(input_group=True))

    with pytest.raises(DesktopContractError):
        gateway.authorize("coordinate_click", {"window_id": WINDOW})


def test_status_reports_guards_always_on():
    gateway = DesktopGateway(make_policy(input_group=True))
    status = gateway.status()

    assert status["r1_destructive_guard"] == "ALWAYS_ON"
    assert status["r2_forbidden_window_guard"] == "ALWAYS_ON"
    assert status["step_budget"] == 50
    assert status["allowlist_size"] == 1
