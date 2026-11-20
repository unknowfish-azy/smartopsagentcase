"""DH-03：driver 的 loopback HTTP 入口（token / 坐标拒绝 / 路由）。"""

from __future__ import annotations

import threading

import httpx
import pytest

from agent.desktop.driver_fake import FakeDriver
from agent.desktop.driver_service import (
    TOKEN_HEADER,
    make_server,
    validate_bind_host,
)
from agent.desktop.element_id import element_id as build_element_id
from agent.desktop.models import UiElement, WindowInfo

TOKEN = "test-token-123"
WINDOW_ID = "hwnd-2002"
SHOT = b"fake-png-bytes"


def make_driver() -> FakeDriver:
    element = UiElement(
        element_id=build_element_id(WINDOW_ID, "button", "保存", (10, 10, 80, 30)),
        role="button",
        name="保存",
        bbox=(10, 10, 80, 30),
    )
    return FakeDriver(
        windows=[
            WindowInfo(
                window_id=WINDOW_ID,
                window_title="无标题 - 记事本",
                process_name="notepad.exe",
            )
        ],
        elements={WINDOW_ID: [element]},
        screenshot_bytes=SHOT,
    )


@pytest.fixture()
def service():
    driver = make_driver()
    server = make_server(driver, TOKEN, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        yield server, driver
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def base_url(server) -> str:
    return f"http://127.0.0.1:{server.server_port}"


def auth() -> dict[str, str]:
    return {TOKEN_HEADER: TOKEN}


# ---------------------------------------------------------------------------
# 绑定与启动约束
# ---------------------------------------------------------------------------

def test_binds_loopback_only(service):
    server, _ = service
    assert server.server_address[0] == "127.0.0.1"


def test_refuses_non_loopback_bind():
    with pytest.raises(ValueError):
        make_server(make_driver(), TOKEN, host="0.0.0.0", port=0)

    with pytest.raises(ValueError):
        validate_bind_host("192.168.1.10")

    assert validate_bind_host("localhost") == "127.0.0.1"


def test_refuses_empty_token():
    with pytest.raises(ValueError):
        make_server(make_driver(), "", host="127.0.0.1", port=0)


# ---------------------------------------------------------------------------
# 鉴权
# ---------------------------------------------------------------------------

def test_health_needs_no_token(service):
    server, _ = service
    response = httpx.get(f"{base_url(server)}/health")

    assert response.status_code == 200
    assert response.json()["driver"] == "fake"


@pytest.mark.parametrize("headers", [{}, {TOKEN_HEADER: "wrong"}])
def test_requests_need_valid_token(service, headers):
    server, _ = service
    response = httpx.get(f"{base_url(server)}/windows", headers=headers)

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------

def test_list_windows(service):
    server, _ = service
    response = httpx.get(f"{base_url(server)}/windows", headers=auth())

    assert response.status_code == 200
    windows = response.json()["windows"]
    assert windows == [
        {
            "window_id": WINDOW_ID,
            "window_title": "无标题 - 记事本",
            "process_name": "notepad.exe",
        }
    ]


def test_observe_returns_elements_and_digest(service):
    server, _ = service
    response = httpx.post(
        f"{base_url(server)}/observe", json={"window_id": WINDOW_ID}, headers=auth()
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_id"] == WINDOW_ID
    assert payload["shot_digest"].startswith("sha256:")
    assert payload["elements"][0]["role"] == "button"
    assert len(payload["elements"][0]["bbox"]) == 4


def test_click_round_trip(service):
    server, driver = service
    element_id = driver.observe(WINDOW_ID).elements[0].element_id
    driver.calls.clear()

    response = httpx.post(
        f"{base_url(server)}/click",
        json={"window_id": WINDOW_ID, "element_id": element_id},
        headers=auth(),
    )

    assert response.status_code == 200
    assert driver.calls == [
        ("click", {"window_id": WINDOW_ID, "element_id": element_id})
    ]


@pytest.mark.parametrize(
    "extra", [{"x": 100}, {"y": 200}, {"coord": "10,10"}, {"position": [1, 2]}]
)
def test_coordinate_payload_is_rejected(service, extra):
    server, driver = service

    response = httpx.post(
        f"{base_url(server)}/click",
        json={"window_id": WINDOW_ID, "element_id": "0123456789abcdef", **extra},
        headers=auth(),
    )

    assert response.status_code == 400
    assert "坐标" in response.json()["error"]
    assert driver.calls == []


def test_missing_window_id_is_400(service):
    server, _ = service

    response = httpx.post(f"{base_url(server)}/observe", json={}, headers=auth())

    assert response.status_code == 400


def test_driver_error_maps_to_409(service):
    server, _ = service

    response = httpx.post(
        f"{base_url(server)}/observe",
        json={"window_id": "hwnd-0000"},
        headers=auth(),
    )

    assert response.status_code == 409
    assert "窗口不存在" in response.json()["error"]


def test_screenshot_returns_png(service):
    server, _ = service

    response = httpx.get(
        f"{base_url(server)}/screenshot",
        params={"window_id": WINDOW_ID},
        headers=auth(),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == SHOT


def test_unknown_path_is_404(service):
    server, _ = service

    assert httpx.get(f"{base_url(server)}/nope", headers=auth()).status_code == 404
    assert (
        httpx.post(f"{base_url(server)}/nope", json={}, headers=auth()).status_code
        == 404
    )
