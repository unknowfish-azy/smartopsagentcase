"""DH-09 远程 driver 客户端：云端 agent 通过 loopback HTTP 操作被控端。

对应 ARCHITECTURE §3.5 模式二：被控端 `driver_service.py` 监听 127.0.0.1:9222，
用 `ssh -R` 映射到云端 127.0.0.1:192XX；云端 agent 只认 loopback 地址，
公网不可见。

红线（与 §3.5 同级）：
1. base_url 只允许 loopback（127.0.0.1 / localhost / ::1），拒绝公网 / 内网地址；
2. 每个请求必须带 `X-Desktop-Token`，token 不进日志；
3. 请求体只传 window_id / element_id，坐标永不过网。

本模块不 import 任何系统控制库，可在阿里云 Linux 上运行。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx

from agent.desktop.driver import DesktopDriver, DesktopDriverError
from agent.desktop.driver_service import TOKEN_HEADER
from agent.desktop.models import UiElement, UiObservation, WindowInfo

ALLOWED_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
DEFAULT_TIMEOUT_SECONDS = 5.0


def _env(name: str) -> str:
    """`DESKTOP_HAND_*` 优先，没设再查 `SMARTOPS_DESKTOP_HAND_*`（项目惯例）。"""

    return os.getenv(f"DESKTOP_HAND_{name}") or os.getenv(
        f"SMARTOPS_DESKTOP_HAND_{name}"
    ) or ""


def validate_base_url(base_url: str) -> str:
    """只接受 loopback 的 http 地址；返回去掉末尾斜杠的地址。"""

    parts = urlsplit(base_url or "")
    if parts.scheme != "http" or not parts.hostname:
        raise ValueError(
            f"driver 地址必须是 http://<loopback>:<port>，收到: {base_url!r}"
        )
    if parts.hostname not in ALLOWED_HOSTS:
        raise ValueError(
            f"driver 地址只允许 loopback，拒绝 {parts.hostname!r}"
            "（隧道外的地址会把 driver 暴露到公网，见 ARCHITECTURE §3.5）"
        )
    if parts.port is None:
        raise ValueError(f"driver 地址必须显式带端口，收到: {base_url!r}")

    # IPv6 字面量必须带方括号，否则拼出的 URL 非法。
    host = f"[{parts.hostname}]" if ":" in parts.hostname else parts.hostname
    return f"http://{host}:{parts.port}"


def _parse_captured_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("captured_at 缺失")
    return datetime.fromisoformat(value)


def _parse_element(raw: Any) -> UiElement:
    if not isinstance(raw, dict):
        raise ValueError("elements 只允许对象")
    return UiElement(
        element_id=raw["element_id"],
        role=raw["role"],
        name=raw.get("name", ""),
        bbox=tuple(raw["bbox"]),
        enabled=bool(raw.get("enabled", True)),
        is_destructive=bool(raw.get("is_destructive", False)),
    )


class HttpDriver(DesktopDriver):
    """被控端 driver 的 HTTP 客户端。一个实例对应一台机器、一个 token。"""

    name = "http"

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        client: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise ValueError("driver token 不能为空")
        self.base_url = validate_base_url(base_url)
        self.token = token
        self._client = client or httpx.Client(timeout=timeout)

    # ------------------------------------------------------------------
    # 装配
    # ------------------------------------------------------------------

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """只查配置，不发网络请求（隧道没起时也能正常装配）。"""

        url = _env("DRIVER_URL")
        token = _env("DRIVER_TOKEN")
        if not url:
            return False, "未配置 DESKTOP_HAND_DRIVER_URL"
        if not token:
            return False, "未配置 DESKTOP_HAND_DRIVER_TOKEN"
        try:
            validate_base_url(url)
        except ValueError as exc:
            return False, str(exc)
        return True, f"远程 driver {url}"

    @classmethod
    def from_env(cls) -> "HttpDriver":
        ok, reason = cls.available()
        if not ok:
            raise ValueError(f"远程 driver 不可用：{reason}")
        return cls(_env("DRIVER_URL"), _env("DRIVER_TOKEN"))

    # ------------------------------------------------------------------
    # HTTP 基础设施
    # ------------------------------------------------------------------

    @property
    def _headers(self) -> dict[str, str]:
        return {TOKEN_HEADER: self.token}

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            return response.text[:200]
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
        return response.text[:200]

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(
                method,
                self.base_url + path,
                headers=self._headers,
                **kwargs,
            )
        except httpx.HTTPError as exc:
            raise DesktopDriverError(
                f"driver 连接失败（{self.base_url}）：{type(exc).__name__}"
            ) from exc

        if response.status_code == 200:
            return response
        if response.status_code == 401:
            raise DesktopDriverError("driver token 无效")
        raise DesktopDriverError(
            f"driver 返回 HTTP {response.status_code}：{self._error_message(response)}"
        )

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", path, json=payload)
        try:
            data = response.json()
        except Exception as exc:
            raise DesktopDriverError(f"driver 返回非 JSON：{path}") from exc
        if not isinstance(data, dict):
            raise DesktopDriverError(f"driver 返回格式非法：{path}")
        return data

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_windows(self) -> list[WindowInfo]:
        response = self._request("GET", "/windows")
        try:
            data = response.json()
        except Exception as exc:
            raise DesktopDriverError("driver 返回非 JSON：/windows") from exc
        try:
            return [
                WindowInfo(
                    window_id=item["window_id"],
                    window_title=item.get("window_title", ""),
                    process_name=item["process_name"],
                )
                for item in data["windows"]
            ]
        except (KeyError, TypeError, ValueError) as exc:
            raise DesktopDriverError(f"driver 返回窗口列表格式非法：{exc}") from exc

    def observe(self, window_id: str) -> UiObservation:
        data = self._post("/observe", {"window_id": window_id})
        try:
            return UiObservation(
                window_id=data["window_id"],
                window_title=data.get("window_title", ""),
                process_name=data["process_name"],
                shot_digest=data["shot_digest"],
                captured_at=_parse_captured_at(data["captured_at"]),
                truncated=bool(data.get("truncated", False)),
                elements=tuple(_parse_element(item) for item in data.get("elements", [])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DesktopDriverError(f"driver 返回观测格式非法：{exc}") from exc

    def screenshot(self, window_id: str) -> bytes:
        response = self._request(
            "GET", "/screenshot", params={"window_id": window_id}
        )
        if not response.content:
            raise DesktopDriverError("driver 返回空截图")
        return response.content

    # ------------------------------------------------------------------
    # 动作（只传 id，不传坐标）
    # ------------------------------------------------------------------

    def click(self, window_id: str, element_id: str) -> None:
        self._post("/click", {"window_id": window_id, "element_id": element_id})

    def type_text(self, window_id: str, element_id: str, text: str) -> None:
        self._post(
            "/type",
            {"window_id": window_id, "element_id": element_id, "text": text},
        )

    def press_key(self, window_id: str, key: str) -> None:
        self._post("/key", {"window_id": window_id, "key": key})

    def focus_window(self, window_id: str) -> None:
        self._post("/focus", {"window_id": window_id})


def driver_from_env() -> DesktopDriver | None:
    """按环境选择 driver：远程地址优先，其次本机 Windows，否则 None。

    只做选择，不做可用性探测——探测交给调用方（driver 没起时装配仍应成功）。
    """

    if _env("DRIVER_URL"):
        return HttpDriver(_env("DRIVER_URL"), _env("DRIVER_TOKEN"))

    try:
        from agent.desktop.driver_windows import WindowsDriver

        if WindowsDriver.available()[0]:
            return WindowsDriver()
    except Exception:  # pragma: no cover - 非 Windows 平台导入即失败
        return None
    return None


__all__ = [
    "ALLOWED_HOSTS",
    "DEFAULT_TIMEOUT_SECONDS",
    "HttpDriver",
    "driver_from_env",
    "validate_base_url",
]
