"""DH-03：假驱动的接口形状（observe → click → observe）。"""

from __future__ import annotations

import pytest

from agent.desktop.driver import DesktopDriver, DesktopDriverError, shot_digest
from agent.desktop.driver_fake import FakeDriver
from agent.desktop.element_id import element_id as build_element_id
from agent.desktop.models import UiElement, WindowInfo

WINDOW_ID = "hwnd-1001"
SHOT = b"fake-png-bytes"


def make_window() -> WindowInfo:
    return WindowInfo(
        window_id=WINDOW_ID,
        window_title="无标题 - 记事本",
        process_name="notepad.exe",
    )


def make_element(name: str = "保存", bbox: tuple[int, int, int, int] = (10, 10, 80, 30)) -> UiElement:
    return UiElement(
        element_id=build_element_id(WINDOW_ID, "button", name, bbox),
        role="button",
        name=name,
        bbox=bbox,
    )


def make_driver() -> FakeDriver:
    element = make_element()
    return FakeDriver(windows=[make_window()], elements={WINDOW_ID: [element]}, screenshot_bytes=SHOT)


def test_fake_driver_is_available():
    assert FakeDriver.available() == (True, "fake driver（仅测试与演示用）")


def test_abstract_driver_is_unavailable():
    ok, reason = DesktopDriver.available()
    assert ok is False
    assert reason


def test_observe_click_observe_round_trip():
    driver = make_driver()

    first = driver.observe(WINDOW_ID)
    assert first.window_id == WINDOW_ID
    assert first.process_name == "notepad.exe"
    assert first.shot_digest == shot_digest(SHOT)
    assert len(first.elements) == 1

    driver.click(WINDOW_ID, first.elements[0].element_id)

    second = driver.observe(WINDOW_ID)
    assert second.shot_digest == first.shot_digest
    assert [call[0] for call in driver.calls] == ["observe", "click", "observe"]


def test_list_windows_and_screenshot():
    driver = make_driver()

    assert [item.window_id for item in driver.list_windows()] == [WINDOW_ID]
    assert driver.screenshot(WINDOW_ID) == SHOT
    assert driver.press_key(WINDOW_ID, "enter") is None
    assert driver.focus_window(WINDOW_ID) is None


def test_unknown_window_is_a_driver_error():
    driver = make_driver()

    with pytest.raises(DesktopDriverError):
        driver.observe("hwnd-9999")


def test_unknown_element_is_a_driver_error():
    driver = make_driver()

    with pytest.raises(DesktopDriverError):
        driver.click(WINDOW_ID, "ffffffffffffffff")


def test_type_records_text():
    driver = make_driver()
    element = make_element()

    driver.type_text(WINDOW_ID, element.element_id, "SmartOps")

    assert driver.calls[-1] == (
        "type",
        {"window_id": WINDOW_ID, "element_id": element.element_id, "text": "SmartOps"},
    )


def test_shot_digest_rejects_empty_bytes():
    with pytest.raises(DesktopDriverError):
        shot_digest(b"")
