"""DH-03：Windows 驱动的可用性探测（不做真机动作，真机冒烟留给 DH-08）。"""

from __future__ import annotations

import platform

import pytest

from agent.desktop.driver import DesktopDriverError
from agent.desktop.driver_windows import (
    MAX_ELEMENTS,
    _PYWINAUTO_KEYS,
    WindowsDriver,
)
from agent.desktop.gateway import ALLOWED_KEYS


def test_available_returns_tuple_and_never_raises():
    ok, reason = WindowsDriver.available()

    assert isinstance(ok, bool)
    assert isinstance(reason, str)
    assert reason


def test_available_matches_platform_reality():
    ok, reason = WindowsDriver.available()

    if platform.system() != "Windows":
        assert ok is False
        assert "非 Windows" in reason


def test_non_windows_platform_degrades_instead_of_crashing(monkeypatch):
    monkeypatch.setattr(
        "agent.desktop.driver_windows.platform.system", lambda: "Linux"
    )

    ok, reason = WindowsDriver.available()

    assert ok is False
    assert "非 Windows" in reason


def test_constructor_refuses_when_unavailable(monkeypatch):
    monkeypatch.setattr(
        WindowsDriver, "available", classmethod(lambda cls: (False, "stub unavailable"))
    )

    with pytest.raises(DesktopDriverError):
        WindowsDriver()


def test_key_mapping_covers_gateway_whitelist():
    """gateway 放行的键位，驱动必须都能翻译，否则会出现"放行但按不出"。"""

    assert set(_PYWINAUTO_KEYS) == set(ALLOWED_KEYS)


def test_no_win_or_meta_key_is_mapped():
    assert not any("win" in key or "meta" in key for key in _PYWINAUTO_KEYS)


def test_element_cap_is_bounded():
    assert 0 < MAX_ELEMENTS <= 1000
