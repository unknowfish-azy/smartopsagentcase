"""DH-03 Windows 驱动：pywinauto + UIA。

实测（2026-11-19，CPython 3.14.3 / Windows 11）：`pywinauto 0.6.9` 可安装，
UIA backend 可枚举窗口，`Pillow 12.2` 可用，因此**不启用** comtypes / pyautogui 回退链。
若某台机器装不上，`available()` 会返回 `(False, 原因)`，不会让服务启动失败。

pywinauto 一律惰性导入：本模块在非 Windows 平台可以安全 import（供 `available()` 探测），
真正碰系统 API 的代码全部在方法内部。

要素（ARCHITECTURE §3）：
- `element_id → 后端控件` 的映射只在本类内部维护，每次 observe 重建；
- 元素 `is_destructive` 一律置 False —— 是否代签由 gateway 按文案判定，不由驱动判。
"""

from __future__ import annotations

import ctypes
import platform
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from agent.desktop.driver import DesktopDriver, DesktopDriverError, shot_digest
from agent.desktop.element_id import element_id as build_element_id
from agent.desktop.models import UiElement, UiObservation, WindowInfo

MAX_ELEMENTS = 300

_WINDOW_PREFIX = "hwnd-"

DIGEST_ERROR_HINT = "截图失败时该步只能判 UNVERIFIED"

# gateway 的白名单键位 → pywinauto send_keys 语法。两者必须一一对应（有单测守着）。
_PYWINAUTO_KEYS: dict[str, str] = {
    "enter": "{ENTER}",
    "tab": "{TAB}",
    "escape": "{ESC}",
    "space": " ",
    "backspace": "{BACKSPACE}",
    "delete": "{DELETE}",
    "up": "{UP}",
    "down": "{DOWN}",
    "left": "{LEFT}",
    "right": "{RIGHT}",
    "home": "{HOME}",
    "end": "{END}",
    "pageup": "{PGUP}",
    "pagedown": "{PGDN}",
    "ctrl+a": "^a",
    "ctrl+c": "^c",
    "ctrl+v": "^v",
    "ctrl+x": "^x",
    "ctrl+z": "^z",
    "ctrl+s": "^s",
    "ctrl+f": "^f",
    "ctrl+w": "^w",
}

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_CF_UNICODETEXT = 13
_GMEM_MOVEABLE = 0x0002


def _list_hwnds() -> list[tuple[int, str, int]]:
    """Win32 枚举顶层窗口（hwnd, title, pid）。

    不用 UIA 的 `Desktop.windows()`：只要桌面里有一个 UIA provider 卡住，
    全局枚举就会一起卡死（DH-08 冒烟实测 >30s 无响应）。Win32 枚举是毫秒级，
    UIA 只在真正需要操作某个窗口时按句柄直连。
    """

    import win32gui
    import win32process

    found: list[tuple[int, str, int]] = []

    def _collect(hwnd: int, _param: Any) -> bool:
        if win32gui.IsWindowVisible(hwnd):
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            found.append((hwnd, win32gui.GetWindowText(hwnd), pid))
        return True

    win32gui.EnumWindows(_collect, None)
    return found


def _activate_window(window: Any) -> None:
    """用 Win32 激活窗口；UIA 的 set_focus 在部分终端会话里会卡死（DH-03 实测）。"""

    try:
        handle = getattr(window.element_info, "handle", None)
    except Exception:
        return
    if not handle:
        return

    import ctypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.ShowWindow(handle, 9)  # SW_RESTORE
    user32.SetForegroundWindow(handle)


def _process_name_from_pid(pid: int) -> str:
    """pid → 可执行文件名（R2 判禁入区要用）。"""

    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(
        _PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
    )
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value.rsplit("\\", 1)[-1]
    finally:
        kernel32.CloseHandle(handle)


def _set_clipboard_text(text: str) -> None:
    """写剪贴板（复制粘贴优于逐字键入，见 ARCHITECTURE §10.3 中文 IME）。"""

    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]

    payload = text.encode("utf-16-le") + b"\x00\x00"

    if not user32.OpenClipboard(None):
        raise ctypes.WinError(ctypes.get_last_error())

    try:
        if not user32.EmptyClipboard():
            raise ctypes.WinError(ctypes.get_last_error())

        handle = kernel32.GlobalAlloc(_GMEM_MOVEABLE, len(payload))
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())

        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise ctypes.WinError(ctypes.get_last_error())

        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)

        if not user32.SetClipboardData(_CF_UNICODETEXT, handle):
            raise ctypes.WinError(ctypes.get_last_error())
        # SetClipboardData 成功后句柄归剪贴板所有，不得再释放。
    finally:
        user32.CloseClipboard()


class WindowsDriver(DesktopDriver):
    name = "windows"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """可用性判定：只看平台与依赖，**不做实时 UIA 枚举**（枚举会阻塞，见 probe）。"""

        if platform.system() != "Windows":
            return False, f"非 Windows 平台：{platform.system()}"

        try:
            import pywinauto  # noqa: F401
        except Exception as exc:  # pragma: no cover - 取决于目标机环境
            return False, f"pywinauto 不可用：{exc}"

        try:
            from PIL import Image  # noqa: F401
        except Exception as exc:  # pragma: no cover
            return False, f"Pillow 不可用（截图需要）：{exc}"

        return True, "ok"

    @classmethod
    def probe(cls) -> tuple[bool, str]:
        """实时探测 UIA 能否枚举窗口。

        UIA 枚举在部分进程环境下会阻塞数百毫秒甚至更久，因此**不进 available()**，
        只供 `desktop.status` 与现场诊断显式调用。
        """

        ok, reason = cls.available()
        if not ok:
            return ok, reason

        try:
            from pywinauto import Desktop

            Desktop(backend="uia").windows()
        except Exception as exc:  # pragma: no cover
            return False, f"UIA 后端不可用：{exc}"

        return True, "ok"

    def __init__(self) -> None:
        ok, reason = self.available()
        if not ok:
            raise DesktopDriverError(f"WindowsDriver 不可用：{reason}")

        self._windows: dict[str, Any] = {}
        self._elements: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _window(self, window_id: str) -> Any:
        """按句柄直连 UIA，不做全局枚举。

        全局枚举可能被任意一个卡死的 UIA provider 拖住；按句柄取窗口是
        毫秒级的，且失败会立刻抛“窗口不存在”。
        """

        if not isinstance(window_id, str) or not window_id.startswith(_WINDOW_PREFIX):
            raise DesktopDriverError(f"window_id 非法：{window_id!r}")

        cached = self._windows.get(window_id)
        if cached is not None:
            return cached

        try:
            hwnd = int(window_id.removeprefix(_WINDOW_PREFIX))
        except ValueError as exc:
            raise DesktopDriverError(f"window_id 非法：{window_id!r}") from exc

        import win32gui

        if not win32gui.IsWindow(hwnd):
            raise DesktopDriverError(f"窗口不存在或已关闭：{window_id}")

        from pywinauto.controls.uiawrapper import UIAWrapper
        from pywinauto.uia_element_info import UIAElementInfo

        try:
            window = UIAWrapper(UIAElementInfo(hwnd))
        except Exception as exc:
            raise DesktopDriverError(f"连接窗口失败：{exc}") from exc

        self._windows[window_id] = window
        return window

    def _element(self, element_id: str) -> Any:
        control = self._elements.get(element_id)
        if control is None:
            raise DesktopDriverError("元素不在当前观测内，请先重新 observe")
        return control

    def _process_name(self, window: Any) -> str:
        try:
            pid = window.element_info.process_id
            return _process_name_from_pid(pid)
        except Exception as exc:
            raise DesktopDriverError(f"读取进程名失败：{exc}") from exc

    @staticmethod
    def _capture(window: Any) -> bytes:
        # pywinauto 的 UIA capture_as_image 在窗口处于后台时可能返回 None 或全黑，
        # 先把它激活（Win32，不经 UIA）。
        _activate_window(window)
        try:
            image = window.capture_as_image()
        except Exception as exc:
            raise DesktopDriverError(f"截图失败（{DIGEST_ERROR_HINT}）：{exc}") from exc

        if image is None:
            raise DesktopDriverError(f"截图失败：返回空图像（{DIGEST_ERROR_HINT}）")

        try:
            buffer = BytesIO()
            image.save(buffer, format="PNG")
            return buffer.getvalue()
        except Exception as exc:
            raise DesktopDriverError(f"截图编码失败：{exc}") from exc

    @staticmethod
    def _build_element(window_id: str, control: Any) -> UiElement | None:
        try:
            info = control.element_info
            role = (getattr(info, "control_type", "") or "").strip().lower()
            if not role:
                return None

            name = (getattr(info, "name", "") or "").strip()
            rect = info.rectangle
            bbox = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
                return None

            try:
                enabled = bool(info.enabled)
            except Exception:
                enabled = True

            return UiElement(
                element_id=build_element_id(window_id, role, name, bbox),
                role=role,
                name=name,
                bbox=bbox,
                enabled=enabled,
                # 代签判定归 gateway，驱动不猜。
                is_destructive=False,
            )
        except DesktopDriverError:
            raise
        except Exception:
            # 单个控件读不到属性就跳过，不让整棵树失败。
            return None

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def list_windows(self) -> list[WindowInfo]:
        result: list[WindowInfo] = []
        for hwnd, title, pid in _list_hwnds():
            if not title.strip():
                # 空标题窗口无法进 R3 白名单，也不适合让 planner 选。
                continue
            try:
                process_name = _process_name_from_pid(pid)
            except Exception:
                # 进程可能刚好退出（或无权限），跳过单个窗口不影响整体。
                continue
            result.append(
                WindowInfo(
                    window_id=f"{_WINDOW_PREFIX}{hwnd}",
                    window_title=title,
                    process_name=process_name,
                )
            )
        return result

    def observe(self, window_id: str) -> UiObservation:
        return self.observe_with_shot(window_id)[0]

    def observe_with_shot(self, window_id: str) -> tuple[UiObservation, bytes]:
        """单次抓屏同时产出元素树与原始 PNG，保证 DH-06 的前后 digest 同帧。"""
        window = self._window(window_id)

        try:
            title = window.window_text() or ""
            process = self._process_name(window)
            png = self._capture(window)
        except DesktopDriverError:
            raise
        except Exception as exc:
            raise DesktopDriverError(f"观测窗口失败：{exc}") from exc

        elements: list[UiElement] = []
        self._elements.clear()
        truncated = False

        try:
            controls = window.descendants()
        except Exception as exc:
            raise DesktopDriverError(f"读取 UIA 元素树失败：{exc}") from exc

        for control in controls:
            if len(elements) >= MAX_ELEMENTS:
                truncated = True
                break

            built = self._build_element(window_id, control)
            if built is None:
                continue

            if built.element_id in self._elements:
                continue

            elements.append(built)
            self._elements[built.element_id] = control

        try:
            observation = UiObservation(
                window_id=window_id,
                window_title=title,
                process_name=process,
                shot_digest=shot_digest(png),
                captured_at=datetime.now(timezone.utc),
                elements=elements,
                truncated=truncated,
            )
        except Exception as exc:
            raise DesktopDriverError(f"观测结果不满足契约：{exc}") from exc
        return observation, png

    def screenshot(self, window_id: str) -> bytes:
        return self._capture(self._window(window_id))

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------

    def focus_window(self, window_id: str) -> None:
        window = self._window(window_id)
        try:
            _activate_window(window)
        except Exception as exc:
            raise DesktopDriverError(f"切换窗口失败：{exc}") from exc

    def click(self, window_id: str, element_id: str) -> None:
        window = self._window(window_id)
        control = self._element(element_id)

        try:
            _activate_window(window)
            control.click_input()
        except Exception as exc:
            raise DesktopDriverError(f"点击失败：{exc}") from exc

    def type_text(self, window_id: str, element_id: str, text: str) -> None:
        window = self._window(window_id)
        control = self._element(element_id)

        try:
            _activate_window(window)
            try:
                control.set_focus()
            except Exception:
                pass
        except Exception as exc:
            raise DesktopDriverError(f"聚焦输入框失败：{exc}") from exc

        clipboard_error: Exception | None = None
        try:
            from pywinauto.keyboard import send_keys

            _set_clipboard_text(text)
            send_keys("^v")
            return
        except Exception as exc:
            clipboard_error = exc

        try:
            control.type_keys(text, with_spaces=True, set_foreground=False)
        except Exception as exc:
            raise DesktopDriverError(
                f"输入失败：剪贴板粘贴失败（{clipboard_error}），逐字键入也失败（{exc}）"
            ) from exc

    def press_key(self, window_id: str, key: str) -> None:
        normalized = key.strip().lower().replace(" ", "")
        mapped = _PYWINAUTO_KEYS.get(normalized)
        if mapped is None:
            raise DesktopDriverError(f"不支持的键位：{key!r}")

        window = self._window(window_id)
        try:
            _activate_window(window)
            from pywinauto.keyboard import send_keys

            send_keys(mapped)
        except Exception as exc:
            raise DesktopDriverError(f"按键失败：{exc}") from exc
