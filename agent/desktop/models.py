"""DH-01 数据契约：WindowInfo / UiElement / UiObservation / UiActionReceipt。

依据 docs/design/desktop-hand/ARCHITECTURE.md §5。

纪律沿用 agent/recovery_contracts：构造即校验、拒绝即抛 DesktopContractError、
不做静默兜底。

本模块必须平台无关——它要能在阿里云 Linux 上被导入，因此不得 import 任何
系统控制库（pywinauto / pyautogui / ctypes），分层铁律见 ARCHITECTURE §3。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from agent.desktop.element_id import ELEMENT_ID_RE


class DesktopContractError(ValueError):
    """对象不满足桌面手契约（字段 / 枚举 / 不变量）。"""


_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_REJECT_REASON_RE = re.compile(r"^R[1-6](_[A-Z0-9_]+)*$")

VERDICTS = ("VERIFIED", "UNVERIFIED", "REJECTED")
ACTIONS = ("observe", "focus_window", "click", "type", "key")
_DIFF_KEYS = frozenset({"appeared", "disappeared", "changed"})

# 拒绝码集合：R1..R6（含 _DETAIL 后缀）+ 能力开关类。
REJECT_REASONS = ("R1", "R2", "R3", "R4", "R5", "R6")
NON_RISK_REJECT_REASONS = frozenset({"INPUT_GROUP_DISABLED", "TOTAL_DISABLED"})

# target 只允许这两个键。坐标一律禁止（ARCHITECTURE §9.1）。
TARGET_KEYS = frozenset({"window_id", "element_id"})
_REQUIRED_TARGET_KEYS = {
    "observe": frozenset({"window_id"}),
    "focus_window": frozenset({"window_id"}),
    "key": frozenset({"window_id"}),
    "click": frozenset({"window_id", "element_id"}),
    "type": frozenset({"window_id", "element_id"}),
}


def is_reject_reason(value: str | None) -> bool:
    """reject_reason 是否合法（R1..R6 及其细分码，或能力开关码）。"""

    if not value:
        return False

    return value in NON_RISK_REJECT_REASONS or bool(_REJECT_REASON_RE.match(value))


def _require_digest(value: Any, field_name: str) -> None:
    if not isinstance(value, str) or not _DIGEST_RE.match(value):
        raise DesktopContractError(
            f"{field_name} 必须是 sha256:<64 hex> 形式，收到: {value!r}"
        )


@dataclass(frozen=True)
class WindowInfo:
    """一个可操作窗口的标识。driver.list_windows() 的返回元素。"""

    window_id: str
    window_title: str
    process_name: str

    def __post_init__(self) -> None:
        if not self.window_id:
            raise DesktopContractError("window_id 不能为空")
        if not self.process_name:
            raise DesktopContractError("process_name 不能为空（R2 依赖它判禁入区）")
        if not isinstance(self.window_title, str):
            raise DesktopContractError("window_title 必须是 str（允许空串）")


@dataclass(frozen=True)
class UiElement:
    element_id: str
    role: str
    name: str
    bbox: tuple[int, int, int, int]
    enabled: bool = True
    is_destructive: bool = False

    def __post_init__(self) -> None:
        if not ELEMENT_ID_RE.match(self.element_id or ""):
            raise DesktopContractError(
                f"element_id 必须是 16 位小写十六进制，收到: {self.element_id!r}"
            )

        if not self.role or not self.role.strip():
            raise DesktopContractError("role 不能为空")

        if not isinstance(self.name, str):
            raise DesktopContractError("name 必须是 str（允许空串）")

        bbox = tuple(self.bbox) if isinstance(self.bbox, list) else self.bbox
        if not isinstance(bbox, tuple) or len(bbox) != 4:
            raise DesktopContractError("bbox 必须是 (x0, y0, x1, y1) 四元组")

        for value in bbox:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DesktopContractError("bbox 必须是非负整数")

        x0, y0, x1, y1 = bbox
        if x1 < x0 or y1 < y0:
            raise DesktopContractError("bbox 必须满足 x1 >= x0 且 y1 >= y0")

        if not isinstance(self.enabled, bool) or not isinstance(self.is_destructive, bool):
            raise DesktopContractError("enabled / is_destructive 必须是 bool")

        object.__setattr__(self, "bbox", bbox)


@dataclass(frozen=True)
class UiObservation:
    window_id: str
    window_title: str
    process_name: str
    shot_digest: str
    captured_at: datetime
    elements: tuple[UiElement, ...] = ()
    truncated: bool = False

    def __post_init__(self) -> None:
        if not self.window_id:
            raise DesktopContractError("window_id 不能为空")

        if not self.process_name:
            raise DesktopContractError("process_name 不能为空")

        if not isinstance(self.window_title, str):
            raise DesktopContractError("window_title 必须是 str（允许空串）")

        _require_digest(self.shot_digest, "shot_digest")

        if not isinstance(self.captured_at, datetime):
            raise DesktopContractError("captured_at 必须是 datetime")

        if self.captured_at.tzinfo is None:
            raise DesktopContractError("captured_at 必须带时区（禁止本地时间裸 datetime）")

        if not isinstance(self.truncated, bool):
            raise DesktopContractError("truncated 必须是 bool")

        elements = tuple(self.elements) if isinstance(self.elements, list) else self.elements
        if not isinstance(elements, tuple):
            raise DesktopContractError("elements 必须是 UiElement 序列")

        for element in elements:
            if not isinstance(element, UiElement):
                raise DesktopContractError("elements 只允许 UiElement")

        seen: set[str] = set()
        for element in elements:
            if element.element_id in seen:
                raise DesktopContractError(
                    f"同一次观测内 element_id 重复: {element.element_id}"
                )
            seen.add(element.element_id)

        # 不变量 1：截断观测必须至少保留一个可动作元素（enabled 且非破坏性），
        # 否则视为观测失败——看不见全貌就别动手。
        if self.truncated and not any(
            element.enabled and not element.is_destructive for element in elements
        ):
            raise DesktopContractError(
                "truncated=True 时必须至少保留一个 enabled 且非破坏性的元素"
            )

        object.__setattr__(self, "elements", elements)

    def as_window(self) -> WindowInfo:
        return WindowInfo(
            window_id=self.window_id,
            window_title=self.window_title,
            process_name=self.process_name,
        )

    def find_element(self, element_id: str) -> UiElement | None:
        for element in self.elements:
            if element.element_id == element_id:
                return element
        return None


@dataclass(frozen=True)
class UiActionReceipt:
    run_id: str
    step: int
    action: str
    target: Mapping[str, str]
    before_shot_digest: str | None
    after_shot_digest: str | None
    element_diff: Mapping[str, list] = field(default_factory=dict)
    verdict: str = "UNVERIFIED"
    reject_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id:
            raise DesktopContractError("run_id 不能为空")

        if isinstance(self.step, bool) or not isinstance(self.step, int) or self.step < 0:
            raise DesktopContractError("step 必须是非负整数")

        if self.action not in ACTIONS:
            raise DesktopContractError(
                f"action 必须是 {ACTIONS} 之一，收到: {self.action!r}"
            )

        if not isinstance(self.target, Mapping):
            raise DesktopContractError("target 必须是映射")

        extra = set(self.target) - TARGET_KEYS
        if extra:
            raise DesktopContractError(
                f"target 只允许键 {sorted(TARGET_KEYS)}，出现: {sorted(extra)}"
                "——坐标（x / y / coord）一律禁止，见 ARCHITECTURE §9.1"
            )

        missing = _REQUIRED_TARGET_KEYS[self.action] - set(self.target)
        if missing:
            raise DesktopContractError(
                f"{self.action} 的 target 缺少键: {sorted(missing)}"
            )

        for key, value in self.target.items():
            if not isinstance(value, str) or not value:
                raise DesktopContractError(f"target.{key} 必须是非空字符串")

        # REJECTED 时允许 before/after 都 None（总开关关 / R5 急停这类"静态"拒绝，
        # 连 driver 都没碰过，自然没有截图）。VERIFIED / UNVERIFIED 必须有 before。
        if self.before_shot_digest is not None:
            _require_digest(self.before_shot_digest, "before_shot_digest")
        elif self.verdict != "REJECTED":
            raise DesktopContractError(
                f"verdict={self.verdict} 时必须提供 before_shot_digest"
            )

        if self.after_shot_digest is not None:
            _require_digest(self.after_shot_digest, "after_shot_digest")

        if self.verdict not in VERDICTS:
            raise DesktopContractError(
                f"verdict 必须是 {VERDICTS} 之一，收到: {self.verdict!r}"
            )

        # 不变量 2：VERIFIED 必须有过截图摘要，否则不得计成功。
        if self.verdict == "VERIFIED" and self.after_shot_digest is None:
            raise DesktopContractError("verdict=VERIFIED 时必须提供 after_shot_digest")

        if self.verdict == "REJECTED":
            if not is_reject_reason(self.reject_reason):
                raise DesktopContractError(
                    f"verdict=REJECTED 的 reject_reason 非法: {self.reject_reason!r}"
                )
        elif self.reject_reason is not None:
            raise DesktopContractError(
                "只有 verdict=REJECTED 才允许带 reject_reason"
            )

        if not isinstance(self.element_diff, Mapping):
            raise DesktopContractError("element_diff 必须是映射")

        extra_diff = set(self.element_diff) - _DIFF_KEYS
        if extra_diff:
            raise DesktopContractError(
                f"element_diff 只允许键 {sorted(_DIFF_KEYS)}，出现: {sorted(extra_diff)}"
            )

        for key, value in self.element_diff.items():
            if not isinstance(value, (list, tuple)):
                raise DesktopContractError(f"element_diff.{key} 必须是列表")
