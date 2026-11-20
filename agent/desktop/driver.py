"""DH-03 驱动层抽象。

铁律 1：只有平台驱动（`driver_windows.py` 等）可以 import 系统控制库，
其余层一律通过本模块的抽象接口调用。

铁律 3：坐标只存在于 driver 内部。`element_id → 后端句柄` 的映射由 driver 自己维护，
每次 `observe` 重建；对外接口既不接受、也不返回坐标。

本模块平台无关，不得 import 任何系统控制库。
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod

from agent.desktop.models import UiObservation, WindowInfo

DIGEST_PREFIX = "sha256:"


class DesktopDriverError(RuntimeError):
    """driver 层统一异常。

    所有系统调用异常都必须转成本异常，不得穿透到 planner（ARCHITECTURE §3）。
    """


def shot_digest(png_bytes: bytes) -> str:
    """截图摘要，形状与 DH-06 的 receipt 一致：`sha256:<64 hex>`。"""

    if not png_bytes:
        raise DesktopDriverError("截图内容为空，无法计算 digest")

    return DIGEST_PREFIX + hashlib.sha256(png_bytes).hexdigest()


class DesktopDriver(ABC):
    """被控端驱动接口。所有方法只谈 id，不谈坐标。"""

    name = "abstract"

    @classmethod
    def available(cls) -> tuple[bool, str]:
        """(是否可用, 原因)。缺依赖或非目标平台一律返回 False，不抛异常。"""

        return False, "抽象基类不可用"

    @abstractmethod
    def list_windows(self) -> list[WindowInfo]:
        raise NotImplementedError

    @abstractmethod
    def observe(self, window_id: str) -> UiObservation:
        raise NotImplementedError

    @abstractmethod
    def click(self, window_id: str, element_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def type_text(self, window_id: str, element_id: str, text: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def press_key(self, window_id: str, key: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def focus_window(self, window_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def screenshot(self, window_id: str) -> bytes:
        raise NotImplementedError

    def observe_with_shot(self, window_id: str) -> tuple[UiObservation, bytes]:
        """观测 + 本次观测对应的原始截图（DH-06 证据用）。

        默认实现分两次抓取并校验 digest 一致；能单次抓取的平台驱动应覆写。
        画面在两次抓取之间发生变化时直接拒绝——宁可没有证据，
        也不接受"元素树与截图不是同一帧"的假证明。
        """
        observation = self.observe(window_id)
        png = self.screenshot(window_id)
        if shot_digest(png) != observation.shot_digest:
            raise DesktopDriverError(
                "元素树与截图不是同一帧：画面在抓取期间发生了变化"
            )
        return observation, png
