"""DH-01：元素树 / 观测 / 动作回执的契约不变量。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from agent.desktop.element_id import ELEMENT_ID_RE, element_id
from agent.desktop.models import (
    DesktopContractError,
    UiActionReceipt,
    UiElement,
    UiObservation,
)

DIGEST = "sha256:" + "0" * 64
WINDOW = "w-notepad-1"


def make_element(
    role: str = "button",
    name: str = "保存",
    bbox: tuple[int, int, int, int] = (10, 10, 80, 30),
    *,
    enabled: bool = True,
    destructive: bool = False,
    window_id: str = WINDOW,
) -> UiElement:
    return UiElement(
        element_id=element_id(window_id, role, name, bbox),
        role=role,
        name=name,
        bbox=bbox,
        enabled=enabled,
        is_destructive=destructive,
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


def make_receipt(**overrides) -> UiActionReceipt:
    payload = {
        "run_id": "run-1",
        "step": 1,
        "action": "click",
        "target": {"window_id": WINDOW, "element_id": "0123456789abcdef"},
        "before_shot_digest": DIGEST,
        "after_shot_digest": DIGEST,
        "element_diff": {"appeared": [], "disappeared": [], "changed": []},
        "verdict": "VERIFIED",
    }
    payload.update(overrides)
    return UiActionReceipt(**payload)


# ---------------------------------------------------------------------------
# element_id 稳定性
# ---------------------------------------------------------------------------

def test_element_id_is_stable_and_16_hex():
    first = element_id(WINDOW, "button", "保存", (10, 10, 80, 30))
    second = element_id(WINDOW, "button", "保存", (10, 10, 80, 30))

    assert first == second
    assert ELEMENT_ID_RE.match(first)


def test_element_id_changes_with_bbox_and_window():
    base = element_id(WINDOW, "button", "保存", (10, 10, 80, 30))

    assert base != element_id(WINDOW, "button", "保存", (10, 40, 80, 60))
    assert base != element_id("w-other", "button", "保存", (10, 10, 80, 30))
    assert base != element_id(WINDOW, "edit", "保存", (10, 10, 80, 30))


def test_element_id_rejects_empty_window_or_role():
    with pytest.raises(ValueError):
        element_id("", "button", "保存", (0, 0, 1, 1))
    with pytest.raises(ValueError):
        element_id(WINDOW, "", "保存", (0, 0, 1, 1))


# ---------------------------------------------------------------------------
# UiElement
# ---------------------------------------------------------------------------

def test_element_accepts_list_bbox_and_normalizes_to_tuple():
    element = UiElement(
        element_id="0123456789abcdef",
        role="button",
        name="保存",
        bbox=[1, 2, 3, 4],
    )
    assert element.bbox == (1, 2, 3, 4)


@pytest.mark.parametrize(
    "bad_bbox",
    [
        (10, 10, 5, 30),
        (10, 10, 80, 5),
        (-1, 0, 10, 10),
        (10, 10, 80),
        (True, 0, 10, 10),
        (10.5, 0, 10, 10),
    ],
)
def test_element_rejects_bad_bbox(bad_bbox):
    with pytest.raises(DesktopContractError):
        UiElement(
            element_id="0123456789abcdef",
            role="button",
            name="保存",
            bbox=bad_bbox,
        )


def test_element_rejects_bad_element_id():
    with pytest.raises(DesktopContractError):
        UiElement(element_id="not-hex", role="button", name="保存", bbox=(0, 0, 1, 1))


def test_element_rejects_empty_role():
    with pytest.raises(DesktopContractError):
        UiElement(
            element_id="0123456789abcdef",
            role="  ",
            name="保存",
            bbox=(0, 0, 1, 1),
        )


# ---------------------------------------------------------------------------
# UiObservation
# ---------------------------------------------------------------------------

def test_observation_find_element_and_as_window():
    element = make_element()
    obs = make_obs(element)

    assert obs.find_element(element.element_id) is element
    assert obs.find_element("ffffffffffffffff") is None
    assert obs.as_window().process_name == "notepad.exe"


def test_observation_rejects_naive_datetime():
    with pytest.raises(DesktopContractError):
        UiObservation(
            window_id=WINDOW,
            window_title="无标题 - 记事本",
            process_name="notepad.exe",
            shot_digest=DIGEST,
            captured_at=datetime.now(),
            elements=[],
        )


def test_observation_rejects_bad_digest():
    with pytest.raises(DesktopContractError):
        UiObservation(
            window_id=WINDOW,
            window_title="无标题 - 记事本",
            process_name="notepad.exe",
            shot_digest="md5:abc",
            captured_at=datetime.now(timezone.utc),
            elements=[],
        )


def test_observation_rejects_duplicate_element_id():
    element = make_element()
    with pytest.raises(DesktopContractError):
        make_obs(element, element)


@pytest.mark.parametrize(
    "elements",
    [
        (),
        (make_element(name="确认支付", destructive=True),),
        (make_element(enabled=False),),
    ],
)
def test_truncated_observation_requires_actionable_element(elements):
    with pytest.raises(DesktopContractError):
        make_obs(*elements, truncated=True)


def test_truncated_observation_ok_with_safe_element():
    obs = make_obs(make_element(), make_element(bbox=(1, 1, 2, 2)), truncated=True)
    assert obs.truncated is True


# ---------------------------------------------------------------------------
# UiActionReceipt
# ---------------------------------------------------------------------------

def test_receipt_verified_requires_after_shot():
    with pytest.raises(DesktopContractError):
        make_receipt(after_shot_digest=None)


def test_receipt_unverified_without_after_shot_is_allowed():
    receipt = make_receipt(after_shot_digest=None, verdict="UNVERIFIED")
    assert receipt.verdict == "UNVERIFIED"


@pytest.mark.parametrize(
    "target",
    [
        {"window_id": WINDOW, "element_id": "0123456789abcdef", "x": "10"},
        {"window_id": WINDOW, "element_id": "0123456789abcdef", "y": "10"},
        {"window_id": WINDOW, "element_id": "0123456789abcdef", "coord": "10,10"},
    ],
)
def test_receipt_target_rejects_coordinates(target):
    with pytest.raises(DesktopContractError):
        make_receipt(target=target)


def test_receipt_target_requires_element_id_for_click():
    with pytest.raises(DesktopContractError):
        make_receipt(target={"window_id": WINDOW})


def test_receipt_key_action_needs_only_window_id():
    receipt = make_receipt(action="key", target={"window_id": WINDOW})
    assert receipt.target == {"window_id": WINDOW}


def test_receipt_rejected_requires_valid_reason():
    with pytest.raises(DesktopContractError):
        make_receipt(verdict="REJECTED", reject_reason=None)

    with pytest.raises(DesktopContractError):
        make_receipt(verdict="REJECTED", reject_reason="NOT_A_CODE")

    receipt = make_receipt(
        verdict="REJECTED",
        reject_reason="R1_DESTRUCTIVE_ELEMENT",
        after_shot_digest=None,
    )
    assert receipt.reject_reason == "R1_DESTRUCTIVE_ELEMENT"


def test_receipt_non_rejected_cannot_carry_reason():
    with pytest.raises(DesktopContractError):
        make_receipt(verdict="VERIFIED", reject_reason="R2")


def test_receipt_rejects_unknown_action_and_bad_diff():
    with pytest.raises(DesktopContractError):
        make_receipt(action="coordinate_click")

    with pytest.raises(DesktopContractError):
        make_receipt(element_diff={"coordinates": []})


def test_receipt_rejects_negative_step():
    with pytest.raises(DesktopContractError):
        make_receipt(step=-1)


def test_receipt_accepts_timezone_free_construction_defaults():
    receipt = make_receipt(step=0, verdict="UNVERIFIED", after_shot_digest=None)
    assert receipt.step == 0
    assert isinstance(receipt.target, dict)


def test_control_layer_does_not_import_system_control_libraries():
    """分层铁律 1：除 driver*.py 外，desktop 包不得引用系统控制库（Linux 上要能导入）。"""

    import ast
    import re
    from pathlib import Path

    import agent.desktop as desktop_package

    forbidden = {
        "pyautogui",
        "pywinauto",
        "ctypes",
        "win32gui",
        "comtypes",
        "pyscreeze",
    }
    # 只有平台驱动和冒烟脚本允许碰系统 API；smoke 是专门测 driver 的，本身就要 import pywinauto。
    exempt = re.compile(r"^(driver_(windows|linux|macos)|smoke_notepad)\.py$")

    for path in Path(desktop_package.__file__).parent.glob("*.py"):
        if exempt.match(path.name):
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = {node.module.split(".")[0]}
            else:
                continue

            assert not (forbidden & modules), f"{path.name} 引入了系统控制库: {modules}"
