"""DH-03 driver 的 loopback HTTP 入口：被控端唯一对外接口。

红线（ARCHITECTURE §3.5，不可配）：
1. 只允许绑定 `127.0.0.1` / `localhost` / `::1`，绑 `0.0.0.0` 直接拒绝启动；
2. 每个请求必须带 `X-Desktop-Token`，常量时间比对；
3. 只接受 `window_id` / `element_id`，出现坐标键（x / y / coord / position）一律 400。

本模块**不 import 任何系统控制库**：driver 由调用方注入，所以能在 Linux 上跑测试。
"""

from __future__ import annotations

import argparse
import hmac
import json
import os
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from agent.desktop.driver import DesktopDriver, DesktopDriverError
from agent.desktop.models import UiObservation

TOKEN_HEADER = "X-Desktop-Token"
ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
COORDINATE_KEYS = frozenset(
    {"x", "y", "coord", "coords", "coordinate", "coordinates", "position", "point"}
)
MAX_BODY_BYTES = 1_000_000
DEFAULT_PORT = 9222


def validate_bind_host(host: str) -> str:
    """loopback 校验。返回实际绑定地址。"""

    if host not in ALLOWED_HOSTS:
        raise ValueError(f"driver 只允许绑定 loopback，拒绝 {host!r}")

    return "127.0.0.1" if host == "localhost" else host


def observation_payload(observation: UiObservation) -> dict[str, Any]:
    return {
        "window_id": observation.window_id,
        "window_title": observation.window_title,
        "process_name": observation.process_name,
        "shot_digest": observation.shot_digest,
        "captured_at": observation.captured_at.isoformat(),
        "truncated": observation.truncated,
        "elements": [
            {
                "element_id": element.element_id,
                "role": element.role,
                "name": element.name,
                "bbox": list(element.bbox),
                "enabled": element.enabled,
                "is_destructive": element.is_destructive,
            }
            for element in observation.elements
        ],
    }


class DriverRequestHandler(BaseHTTPRequestHandler):
    server_version = "SmartOpsDesktopDriver/1.0"

    driver: DesktopDriver
    token: str

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------

    def log_message(self, format: str, *args: Any) -> None:
        # 不记录请求体与 token。
        return

    def _authorized(self) -> bool:
        provided = self.headers.get(TOKEN_HEADER, "")
        if not provided or not self.token:
            return False
        return hmac.compare_digest(provided, self.token)

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise ValueError("Content-Length 非法") from exc

        if length <= 0 or length > MAX_BODY_BYTES:
            raise ValueError("请求体为空或过大")

        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except Exception as exc:
            raise ValueError(f"请求体不是合法 JSON：{exc}") from exc

        if not isinstance(data, dict):
            raise ValueError("请求体必须是 JSON 对象")

        forbidden = COORDINATE_KEYS & set(data)
        if forbidden:
            raise ValueError(f"禁止坐标参数：{sorted(forbidden)}，只接受 element_id")

        return data

    def _handle(self, action: Callable[[], Any]) -> None:
        try:
            self._send_json(200, action())
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
        except DesktopDriverError as exc:
            self._send_json(409, {"error": str(exc)})
        except Exception as exc:  # pragma: no cover - 兜底，不外泄栈
            self._send_json(500, {"error": type(exc).__name__})

    # ------------------------------------------------------------------
    # 取值
    # ------------------------------------------------------------------

    @staticmethod
    def _window_id(data: dict[str, Any]) -> str:
        window_id = data.get("window_id")
        if not isinstance(window_id, str) or not window_id:
            raise ValueError("window_id 必填")
        return window_id

    @staticmethod
    def _element_id(data: dict[str, Any]) -> str:
        element_id = data.get("element_id")
        if not isinstance(element_id, str) or not element_id:
            raise ValueError("element_id 必填")
        return element_id

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)

        if parsed.path == "/health":
            self._send_json(
                200, {"ok": True, "driver": getattr(self.driver, "name", "unknown")}
            )
            return

        if not self._authorized():
            self._send_json(401, {"error": "token 无效"})
            return

        if parsed.path == "/windows":
            self._handle(lambda: {"windows": [asdict(item) for item in self.driver.list_windows()]})
            return

        if parsed.path == "/screenshot":
            window_id = (parse_qs(parsed.query).get("window_id") or [""])[0]
            if not window_id:
                self._send_json(400, {"error": "window_id 必填"})
                return

            try:
                self._send_bytes(200, self.driver.screenshot(window_id), "image/png")
            except DesktopDriverError as exc:
                self._send_json(409, {"error": str(exc)})
            except Exception as exc:  # pragma: no cover
                self._send_json(500, {"error": type(exc).__name__})
            return

        self._send_json(404, {"error": "未知路径"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            self._send_json(401, {"error": "token 无效"})
            return

        try:
            data = self._read_json()
        except ValueError as exc:
            self._send_json(400, {"error": str(exc)})
            return

        path = urlparse(self.path).path

        if path == "/observe":
            self._handle(
                lambda: observation_payload(self.driver.observe(self._window_id(data)))
            )
            return

        if path == "/click":
            self._handle(lambda: self._click(data))
            return

        if path == "/type":
            self._handle(lambda: self._type(data))
            return

        if path == "/key":
            self._handle(lambda: self._key(data))
            return

        if path == "/focus":
            self._handle(lambda: self._focus(data))
            return

        self._send_json(404, {"error": "未知路径"})

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------

    def _click(self, data: dict[str, Any]) -> dict[str, Any]:
        self.driver.click(self._window_id(data), self._element_id(data))
        return {"ok": True}

    def _type(self, data: dict[str, Any]) -> dict[str, Any]:
        window_id = self._window_id(data)
        element_id = self._element_id(data)
        text = data.get("text")
        if not isinstance(text, str):
            raise ValueError("text 必填且必须是字符串")
        self.driver.type_text(window_id, element_id, text)
        return {"ok": True}

    def _key(self, data: dict[str, Any]) -> dict[str, Any]:
        window_id = self._window_id(data)
        key = data.get("key")
        if not isinstance(key, str) or not key:
            raise ValueError("key 必填")
        self.driver.press_key(window_id, key)
        return {"ok": True}

    def _focus(self, data: dict[str, Any]) -> dict[str, Any]:
        self.driver.focus_window(self._window_id(data))
        return {"ok": True}


def make_server(
    driver: DesktopDriver,
    token: str,
    host: str = "127.0.0.1",
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("driver 必须配置 token，禁止空 token 启动")

    bind_host = validate_bind_host(host)
    handler = type(
        "BoundDriverHandler",
        (DriverRequestHandler,),
        {"driver": driver, "token": token},
    )

    server = ThreadingHTTPServer((bind_host, port), handler)
    server.daemon_threads = True
    return server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SmartOps 桌面手 driver（只监听 loopback 的 HTTP 服务）"
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("DESKTOP_HAND_DRIVER_PORT", str(DEFAULT_PORT))),
    )
    parser.add_argument("--token", default=os.getenv("DESKTOP_HAND_DRIVER_TOKEN", ""))
    args = parser.parse_args(argv)

    from agent.desktop.driver_windows import WindowsDriver

    ok, reason = WindowsDriver.available()
    if not ok:
        raise SystemExit(f"桌面手 driver 不可用：{reason}")

    server = make_server(WindowsDriver(), args.token, args.host, args.port)
    print(
        f"desktop driver listening on http://{args.host}:{server.server_port}",
        flush=True,
    )
    server.serve_forever()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
