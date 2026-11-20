"""DH-09：远程 driver 客户端（loopback 限制 / token / 契约往返）。

真两端：用 `make_server` + `FakeDriver` 起一个真实的 loopback HTTP 服务，
再用 `HttpDriver` 走一遍完整协议——客户端与服务端任何一侧改协议都会红。
"""

from __future__ import annotations

import threading

import pytest

from agent.desktop.driver import DesktopDriverError
from agent.desktop.driver_fake import FakeDriver
from agent.desktop.driver_http import HttpDriver, driver_from_env, validate_base_url
from agent.desktop.driver_service import make_server
from agent.desktop.element_id import element_id as build_element_id
from agent.desktop.models import UiElement, WindowInfo

TOKEN = "test-token-123"
WINDOW_ID = "hwnd-3003"
SHOT = b"http-round-trip-png"
ELEMENT_ID = build_element_id(WINDOW_ID, "button", "保存", (10, 10, 80, 30))


def make_driver() -> FakeDriver:
    return FakeDriver(
        windows=[
            WindowInfo(
                window_id=WINDOW_ID,
                window_title="无标题 - 记事本",
                process_name="notepad.exe",
            )
        ],
        elements={
            WINDOW_ID: [
                UiElement(
                    element_id=ELEMENT_ID,
                    role="button",
                    name="保存",
                    bbox=(10, 10, 80, 30),
                )
            ]
        },
        screenshot_bytes=SHOT,
    )


@pytest.fixture()
def endpoint():
    driver = make_driver()
    server = make_server(driver, TOKEN, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield f"http://127.0.0.1:{server.server_port}", driver
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


# ---------------------------------------------------------------------------
# 地址与 token 约束
# ---------------------------------------------------------------------------

def test_loopback_only():
    assert validate_base_url("http://127.0.0.1:19222/") == "http://127.0.0.1:19222"
    assert validate_base_url("http://localhost:19222") == "http://localhost:19222"
    # IPv6 字面量必须保留方括号，否则拼出的 URL 非法。
    assert validate_base_url("http://[::1]:19222") == "http://[::1]:19222"


@pytest.mark.parametrize(
    "url",
    [
        "http://10.0.0.5:19222",
        "http://47.100.1.1:19222",
        "https://127.0.0.1:19222",
        "127.0.0.1:19222",
        "http://127.0.0.1",
    ],
)
def test_rejects_non_loopback_or_bad_url(url):
    with pytest.raises(ValueError):
        validate_base_url(url)

    with pytest.raises(ValueError):
        HttpDriver(url, TOKEN)


def test_requires_token(endpoint):
    base_url, _ = endpoint
    with pytest.raises(ValueError):
        HttpDriver(base_url, "")


# ---------------------------------------------------------------------------
# 协议往返
# ---------------------------------------------------------------------------

def test_list_windows(endpoint):
    base_url, _ = endpoint
    windows = HttpDriver(base_url, TOKEN).list_windows()

    assert windows == [
        WindowInfo(
            window_id=WINDOW_ID,
            window_title="无标题 - 记事本",
            process_name="notepad.exe",
        )
    ]


def test_observe_round_trip(endpoint):
    base_url, _ = endpoint
    observation = HttpDriver(base_url, TOKEN).observe(WINDOW_ID)

    assert observation.window_id == WINDOW_ID
    assert observation.process_name == "notepad.exe"
    assert observation.truncated is False
    assert observation.captured_at.tzinfo is not None
    assert [element.element_id for element in observation.elements] == [ELEMENT_ID]
    assert observation.elements[0].bbox == (10, 10, 80, 30)


def test_observe_with_shot_verifies_digest(endpoint):
    base_url, _ = endpoint
    observation, png = HttpDriver(base_url, TOKEN).observe_with_shot(WINDOW_ID)

    assert png == SHOT
    assert observation.shot_digest.startswith("sha256:")


def test_actions_round_trip(endpoint):
    base_url, driver = endpoint
    http = HttpDriver(base_url, TOKEN)
    driver.calls.clear()

    http.focus_window(WINDOW_ID)
    http.click(WINDOW_ID, ELEMENT_ID)
    http.type_text(WINDOW_ID, ELEMENT_ID, "巡检完成")
    http.press_key(WINDOW_ID, "ctrl+s")

    assert driver.calls == [
        ("focus_window", {"window_id": WINDOW_ID}),
        ("click", {"window_id": WINDOW_ID, "element_id": ELEMENT_ID}),
        ("type", {"window_id": WINDOW_ID, "element_id": ELEMENT_ID, "text": "巡检完成"}),
        ("key", {"window_id": WINDOW_ID, "key": "ctrl+s"}),
    ]


# ---------------------------------------------------------------------------
# 失败路径
# ---------------------------------------------------------------------------

def test_wrong_token_becomes_driver_error(endpoint):
    base_url, _ = endpoint
    http = HttpDriver(base_url, "wrong-token")

    with pytest.raises(DesktopDriverError, match="token"):
        http.list_windows()


def test_driver_error_maps_to_driver_error(endpoint):
    base_url, _ = endpoint
    http = HttpDriver(base_url, TOKEN)

    with pytest.raises(DesktopDriverError, match="窗口不存在"):
        http.observe("hwnd-0000")


def test_unreachable_endpoint_becomes_driver_error():
    http = HttpDriver("http://127.0.0.1:1", TOKEN, timeout=0.5)

    with pytest.raises(DesktopDriverError, match="连接失败"):
        http.list_windows()


# ---------------------------------------------------------------------------
# 环境装配
# ---------------------------------------------------------------------------

def test_available_reads_env(monkeypatch, endpoint):
    base_url, _ = endpoint
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_URL", base_url)
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_TOKEN", TOKEN)

    ok, _ = HttpDriver.available()
    assert ok is True

    driver = HttpDriver.from_env()
    assert isinstance(driver, HttpDriver)
    assert driver.base_url == base_url


def test_available_missing_token(monkeypatch, endpoint):
    base_url, _ = endpoint
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_URL", base_url)
    monkeypatch.delenv("DESKTOP_HAND_DRIVER_TOKEN", raising=False)
    monkeypatch.delenv("SMARTOPS_DESKTOP_HAND_DRIVER_TOKEN", raising=False)

    ok, reason = HttpDriver.available()
    assert ok is False
    assert "TOKEN" in reason


def test_smartops_prefix_as_fallback(monkeypatch, endpoint):
    base_url, _ = endpoint
    monkeypatch.delenv("DESKTOP_HAND_DRIVER_URL", raising=False)
    monkeypatch.setenv("SMARTOPS_DESKTOP_HAND_DRIVER_URL", base_url)
    monkeypatch.setenv("SMARTOPS_DESKTOP_HAND_DRIVER_TOKEN", TOKEN)

    assert HttpDriver.available()[0] is True


def test_driver_from_env_prefers_remote(monkeypatch, endpoint):
    base_url, _ = endpoint
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_URL", base_url)
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_TOKEN", TOKEN)

    driver = driver_from_env()
    assert isinstance(driver, HttpDriver)


def test_driver_from_env_rejects_non_loopback(monkeypatch):
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_URL", "http://8.8.8.8:19222")
    monkeypatch.setenv("DESKTOP_HAND_DRIVER_TOKEN", TOKEN)

    with pytest.raises(ValueError, match="loopback"):
        driver_from_env()
