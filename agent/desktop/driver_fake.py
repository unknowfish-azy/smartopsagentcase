"""DH-03 假驱动：只用于测试与本地演示，不碰任何系统 API。

放在 `agent/` 下是为了让 DH-05 的工具面测试也能复用它（真实驱动需要 Windows + UIA）。
"""

from __future__ import annotations

from datetime import datetime, timezone

from agent.desktop.driver import DesktopDriver, DesktopDriverError, shot_digest
from agent.desktop.models import UiElement, UiObservation, WindowInfo


class FakeDriver(DesktopDriver):
    name = "fake"

    def __init__(
        self,
        windows: list[WindowInfo] | None = None,
        elements: dict[str, list[UiElement]] | None = None,
        screenshot_bytes: bytes = b"fake-png-bytes",
    ) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._windows = list(windows or [])
        self._elements = dict(elements or {})
        self._shot = screenshot_bytes

    @classmethod
    def available(cls) -> tuple[bool, str]:
        return True, "fake driver（仅测试与演示用）"

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_windows(self) -> list[WindowInfo]:
        return list(self._windows)

    def _window(self, window_id: str) -> WindowInfo:
        for window in self._windows:
            if window.window_id == window_id:
                return window
        raise DesktopDriverError(f"窗口不存在：{window_id}")

    def observe(self, window_id: str) -> UiObservation:
        window = self._window(window_id)
        self.calls.append(("observe", {"window_id": window_id}))
        return UiObservation(
            window_id=window.window_id,
            window_title=window.window_title,
            process_name=window.process_name,
            shot_digest=shot_digest(self._shot),
            captured_at=datetime.now(timezone.utc),
            elements=self._elements.get(window_id, []),
        )

    def screenshot(self, window_id: str) -> bytes:
        self._window(window_id)
        self.calls.append(("screenshot", {"window_id": window_id}))
        return self._shot

    def observe_with_shot(self, window_id: str) -> tuple[UiObservation, bytes]:
        # 单帧来源：元素树与截图用的就是同一份 bytes，digest 必然一致。
        return self.observe(window_id), self._shot

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------

    def _element(self, window_id: str, element_id: str) -> UiElement:
        for element in self._elements.get(window_id, []):
            if element.element_id == element_id:
                return element
        raise DesktopDriverError(f"元素不在当前观测内：{element_id}")

    def click(self, window_id: str, element_id: str) -> None:
        self._window(window_id)
        self._element(window_id, element_id)
        self.calls.append(
            ("click", {"window_id": window_id, "element_id": element_id})
        )

    def type_text(self, window_id: str, element_id: str, text: str) -> None:
        self._window(window_id)
        self._element(window_id, element_id)
        self.calls.append(
            ("type", {"window_id": window_id, "element_id": element_id, "text": text})
        )

    def press_key(self, window_id: str, key: str) -> None:
        self._window(window_id)
        self.calls.append(("key", {"window_id": window_id, "key": key}))

    def focus_window(self, window_id: str) -> None:
        self._window(window_id)
        self.calls.append(("focus_window", {"window_id": window_id}))
