"""DH-05 桌面手工具面：六个工具，全部走 `gateway.authorize` 前置。

铁律 2：本模块**不做任何策略判断**——能不能点、能不能输入只由 gateway 回答，
这里只把结果如实转成结构化 Observation 返回，拒绝码原样保留。
铁律 3：LLM 可见的 schema 里只有 `window_id` / `element_id`，没有 `x` / `y`。

刻意不暴露的两个能力（ARCHITECTURE §9）：
* `desktop.resume`：急停恢复只能由人做（R5），Agent 拿不到一次性 token；
* `desktop.coordinate_click`：纯坐标点击会让 R1/R2/R3 全部失效。

驱动通过构造参数注入：生产环境是本机 `WindowsDriver` 或指向被控端 loopback
driver 服务的客户端，测试用 `FakeDriver`。本模块不感知部署形态。
"""

from __future__ import annotations

from typing import Any, Callable

from agent.desktop.driver import DesktopDriver
from agent.desktop.gateway import DesktopGateway, Decision
from agent.desktop.models import UiObservation, WindowInfo
from agent.desktop.receipts import (
    DesktopReceiptLog,
    ShotStore,
    build_receipt,
    ensure_observation_pair,
    receipt_payload,
)
from agent.policies.risk import RiskLevel
from agent.sdk.tool import ImplementationStatus, ToolDefinition

# 拒绝码前缀 → 给 Agent / 运维看的说明。reject_reason 原码始终一并返回。
_REJECT_HINTS: tuple[tuple[str, str], ...] = (
    ("R1", "命中代签/危险文案，绝对禁止（不可配置）"),
    ("R2", "目标窗口或按键属于禁入区（cmd / regedit / taskmgr 等）"),
    ("R3", "窗口不在白名单，或元素 role 未被允许"),
    ("R4", "动作预算 / 限速 / 连续同元素点击触发"),
    ("R5", "急停锁定中，只能由人恢复"),
    ("R6", "观测缺失或不完整（截断 / 窗口不匹配 / 元素未知）"),
    ("INPUT_GROUP_DISABLED", "输入组默认关闭，需人工开启后才能点击 / 输入"),
)


def _hint(reject_reason: str | None) -> str:
    if not reject_reason:
        return "被门禁拒绝"
    for prefix, text in _REJECT_HINTS:
        if reject_reason.startswith(prefix):
            return text
    return "被门禁拒绝"


def _require_text(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} 必须是非空字符串")
    return value


def _guarded(action: str, call: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """工具统一兜底：driver / 契约异常转结构化错误，不让 Agent 循环中断。"""
    try:
        return call()
    except Exception as exc:  # noqa: BLE001 - 工具层边界，错误必须变成 Observation
        return {"ok": False, "action": action, "error": f"{type(exc).__name__}: {exc}"}


def _rejected(action: str, target: dict[str, str], decision: Decision) -> dict[str, Any]:
    return {
        "ok": False,
        "action": action,
        "target": dict(target),
        "rejected": True,
        "reject_reason": decision.reject_reason,
        "message": _hint(decision.reject_reason),
    }


def _observation_payload(obs: UiObservation) -> dict[str, Any]:
    """观测 → 可 JSON 序列化的元素树（不含图片字节）。"""
    return {
        "window_id": obs.window_id,
        "window_title": obs.window_title,
        "process_name": obs.process_name,
        "shot_digest": obs.shot_digest,
        "captured_at": obs.captured_at.isoformat(),
        "truncated": obs.truncated,
        "elements": [
            {
                "element_id": element.element_id,
                "role": element.role,
                "name": element.name,
                "bbox": list(element.bbox),
                "enabled": element.enabled,
                "is_destructive": element.is_destructive,
            }
            for element in obs.elements
        ],
    }


class DesktopHand:
    """一个会话的桌面手：driver + gateway 的组合，工具只和它交互。

    gateway 是有状态的（预算 / 限速 / 急停），因此一个会话必须共用一个实例。
    """

    def __init__(
        self,
        driver: DesktopDriver,
        gateway: DesktopGateway | None = None,
        *,
        run_id: str = "desktop-run",
        shot_store: ShotStore | None = None,
        receipt_log: DesktopReceiptLog | None = None,
    ) -> None:
        self.driver = driver
        self.gateway = gateway or DesktopGateway()
        self.run_id = run_id
        # 两者为 None 时不落盘：工具层不猜生产路径，由装配层注入。
        self.shots = shot_store
        self.receipts = receipt_log
        self._step = 0

    # ------------------------------------------------------------------
    # 动作
    # ------------------------------------------------------------------

    def observe(self, window_id: str) -> dict[str, Any]:
        # 先 authorize（总开关关 / R2 / R3 在这一步就被拦下），
        # 再 observe；顺序不能反——gateway 需要进程名 / 标题做 R2/R3 判定。
        # 总开关关时 _no_driver_rejection 会在不碰 driver 的情况下产 REJECTED receipt。
        if not self.gateway._enabled:
            return self._no_driver_rejection(
                "observe", {"window_id": window_id}, "TOTAL_DISABLED"
            )

        window = self._window(window_id)
        decision = self.gateway.authorize("observe", {"window_id": window_id}, window=window)
        if not decision.allowed:
            return self._with_receipt(
                _rejected("observe", {"window_id": window_id}, decision)
            )

        # observe 也要产 receipt：用 observe_with_shot 拿 before/after，
        # 画面没变化时 verdict=UNVERIFIED（符合 contract），但账本里有完整证据链。
        obs, png = self.driver.observe_with_shot(window_id)
        receipt = self._record(
            "observe",
            {"window_id": window_id},
            obs,
            png,
        )
        return {
            "ok": True,
            "action": "observe",
            **_observation_payload(obs),
            "receipt": receipt,
        }

    def focus_window(self, window_id: str) -> dict[str, Any]:
        # 总开关关直接拒绝，不碰 driver
        if not self.gateway._enabled:
            target = {"window_id": window_id}
            return self._no_driver_rejection("focus_window", target, "TOTAL_DISABLED")

        target = {"window_id": window_id}
        before, before_png = self.driver.observe_with_shot(window_id)

        self.driver.focus_window(window_id)
        after, after_png = self.driver.observe_with_shot(window_id)
        return {
            "ok": True,
            "action": "focus_window",
            "window_id": window_id,
            "receipt": self._record(
                "focus_window", target, before, before_png, after, after_png
            ),
        }

    def click(self, window_id: str, element_id: str) -> dict[str, Any]:
        target = {"window_id": window_id, "element_id": element_id}
        if not self.gateway._enabled:
            return self._no_driver_rejection("click", target, "TOTAL_DISABLED")
        # R6/R3/R1 都依赖元素树，输入动作必须先观测；观测失败即拒绝，绝不盲点。
        before, before_png = self.driver.observe_with_shot(window_id)
        decision = self.gateway.authorize("click", target, obs=before)
        if not decision.allowed:
            rejected = _rejected("click", target, decision)
            rejected["receipt"] = self._record(
                "click", target, before, before_png,
                reject_reason=decision.reject_reason,
            )
            return rejected

        self.driver.click(window_id, element_id)
        after, after_png = self.driver.observe_with_shot(window_id)
        return {
            "ok": True,
            "action": "click",
            "target": target,
            "before_shot_digest": before.shot_digest,
            "receipt": self._record("click", target, before, before_png, after, after_png),
        }

    def type_text(self, window_id: str, element_id: str, text: str) -> dict[str, Any]:
        target = {"window_id": window_id, "element_id": element_id}
        if not self.gateway._enabled:
            return self._no_driver_rejection("type", target, "TOTAL_DISABLED")
        before, before_png = self.driver.observe_with_shot(window_id)
        decision = self.gateway.authorize("type", target, obs=before)
        if not decision.allowed:
            rejected = _rejected("type", target, decision)
            rejected["receipt"] = self._record(
                "type", target, before, before_png,
                reject_reason=decision.reject_reason,
            )
            return rejected

        self.driver.type_text(window_id, element_id, text)
        after, after_png = self.driver.observe_with_shot(window_id)
        return {
            "ok": True,
            "action": "type",
            "target": target,
            "chars": len(text),
            "before_shot_digest": before.shot_digest,
            "receipt": self._record("type", target, before, before_png, after, after_png),
        }

    def press_key(self, window_id: str, key: str) -> dict[str, Any]:
        target = {"window_id": window_id}
        if not self.gateway._enabled:
            return self._no_driver_rejection("key", target, "TOTAL_DISABLED")
        before, before_png = self.driver.observe_with_shot(window_id)
        decision = self.gateway.authorize("key", target, obs=before, key=key)
        if not decision.allowed:
            rejected = _rejected("key", target, decision)
            rejected["receipt"] = self._record(
                "key", target, before, before_png,
                reject_reason=decision.reject_reason,
            )
            return rejected

        self.driver.press_key(window_id, key)
        after, after_png = self.driver.observe_with_shot(window_id)
        return {
            "ok": True,
            "action": "key",
            "target": target,
            "key": key,
            "before_shot_digest": before.shot_digest,
            "receipt": self._record("key", target, before, before_png, after, after_png),
        }

    def status(self) -> dict[str, Any]:
        available, reason = self.driver.available()
        return {
            "ok": True,
            "driver": {
                "name": getattr(self.driver, "name", "unknown"),
                "available": available,
                "reason": reason,
            },
            "gateway": self.gateway.status(),
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _no_driver_rejection(
        self,
        action: str,
        target: dict[str, str],
        reject_reason: str,
    ) -> dict[str, Any]:
        """总开关关 / R5 急停 等"静态"拒绝：不碰 driver 也能产 REJECTED receipt。

        没碰 driver → 没有 before 截图 → before_shot_digest=None，
        这是 contract 允许的（REJECTED 时 before/after 都可以 None）。
        """
        self._step += 1
        receipt = build_receipt(
            run_id=self.run_id,
            step=self._step,
            action=action,
            target=target,
            before_digest=None,
            after_digest=None,
            reject_reason=reject_reason,
        )
        if self.receipts is not None:
            self.receipts.append(receipt)
        return {
            "ok": False,
            "action": action,
            "target": target,
            "rejected": True,
            "reject_reason": reject_reason,
            "message": _hint(reject_reason),
            "receipt": receipt_payload(receipt),
        }

    def _with_receipt(self, result: dict[str, Any]) -> dict[str, Any]:
        """给没有 driver 交互的 rejection 补一张空 REJECTED receipt。

        现在的 observe / focus_window 在静态门禁（R2 / R3 / R5）拒绝时还没碰 driver，
        所以 before_digest=None——与 _no_driver_rejection 同一条契约。
        """
        if result.get("receipt") is not None:
            return result
        self._step += 1
        receipt = build_receipt(
            run_id=self.run_id,
            step=self._step,
            action=result.get("action", ""),
            target=result.get("target", {}),
            before_digest=None,
            after_digest=None,
            reject_reason=result.get("reject_reason"),
        )
        if self.receipts is not None:
            self.receipts.append(receipt)
        result = dict(result)
        result["receipt"] = receipt_payload(receipt)
        return result

    def _record(
        self,
        action: str,
        target: dict[str, str],
        before: UiObservation,
        before_png: bytes,
        after: UiObservation | None = None,
        after_png: bytes | None = None,
        reject_reason: str | None = None,
    ) -> dict[str, Any]:
        """构造回执 → 截图落盘 → 追加账本，返回不含图片字节的 receipt 载荷。

        拒绝也要记：`REJECTED` 回执是"门禁确实拦住了"的证据，不是噪声。
        """
        self._step += 1
        if after is not None:
            ensure_observation_pair(before, after)

        shots: dict[str, str] = {}
        if self.shots is not None:
            shots["before"] = self.shots.save(
                self.run_id, self._step, "before", before_png,
                expected_digest=before.shot_digest,
            )
            if after is not None and after_png is not None:
                shots["after"] = self.shots.save(
                    self.run_id, self._step, "after", after_png,
                    expected_digest=after.shot_digest,
                )

        receipt = build_receipt(
            run_id=self.run_id,
            step=self._step,
            action=action,
            target=target,
            before_digest=before.shot_digest,
            after_digest=after.shot_digest if after is not None else None,
            before_elements=before.elements,
            after_elements=after.elements if after is not None else (),
            reject_reason=reject_reason,
        )
        if self.receipts is not None:
            self.receipts.append(receipt, shots)

        payload = receipt_payload(receipt)
        if shots:
            payload["shots"] = shots
        return payload

    def _window(self, window_id: str) -> WindowInfo:
        """从 driver 的窗口表取 WindowInfo（R2/R3 需要进程名与标题）。"""
        for window in self.driver.list_windows():
            if window.window_id == window_id:
                return window
        raise ValueError(f"窗口不存在或不可见：{window_id}")


class _DesktopTool:
    """旧式同步工具（`execute(**arguments)`），与 ServerStatusTool 同一调用契约。

    额外挂一个 `ToolDefinition`：executor 用它做 input_schema 校验与超时预算，
    planner 用它生成工具目录；`risk_level` / `requires_approval` 保持类属性，
    与既有内置工具一致。
    """

    name = ""
    description = ""
    risk_level = RiskLevel.LOW
    requires_approval = False
    schema: dict[str, Any] = {"type": "object", "properties": {}}
    deadline_ms = 20_000
    idempotency = "SAFE_RETRY"
    verification = "动作前后由 DH-06 receipt 校验（当前仅回 shot_digest）"

    def __init__(self, hand: DesktopHand) -> None:
        self.hand = hand
        self.definition = ToolDefinition(
            name=self.name,
            description=self.description,
            risk=self.risk_level,
            target_type="DESKTOP",
            input_schema=self.schema,
            deadline_ms=self.deadline_ms,
            idempotency=self.idempotency,
            verification=self.verification,
        )

    def execute(self, **arguments: Any) -> dict[str, Any]:
        raise NotImplementedError


class DesktopObserveTool(_DesktopTool):
    name = "desktop.observe"
    description = "只读观测：返回窗口元素树 + 截图摘要（不含图片字节）"
    schema = {
        "type": "object",
        "properties": {
            "window_id": {"type": "string", "description": "driver 返回的窗口 id"},
        },
        "required": ["window_id"],
    }

    def execute(self, **arguments: Any) -> dict[str, Any]:
        return _guarded(
            self.name, lambda: self.hand.observe(_require_text(arguments, "window_id"))
        )


class DesktopFocusWindowTool(_DesktopTool):
    name = "desktop.focus_window"
    description = "把指定窗口切到前台（不点击任何元素）"
    risk_level = RiskLevel.MEDIUM
    schema = {
        "type": "object",
        "properties": {
            "window_id": {"type": "string", "description": "driver 返回的窗口 id"},
        },
        "required": ["window_id"],
    }

    def execute(self, **arguments: Any) -> dict[str, Any]:
        return _guarded(
            self.name, lambda: self.hand.focus_window(_require_text(arguments, "window_id"))
        )


class DesktopClickTool(_DesktopTool):
    name = "desktop.click"
    description = "点击一个元素（只接受 element_id，坐标在 driver 内部解析）"
    risk_level = RiskLevel.HIGH
    requires_approval = True
    schema = {
        "type": "object",
        "properties": {
            "window_id": {"type": "string", "description": "driver 返回的窗口 id"},
            "element_id": {"type": "string", "description": "desktop.observe 返回的元素 id"},
        },
        "required": ["window_id", "element_id"],
    }
    idempotency = "AT_MOST_ONCE"

    def execute(self, **arguments: Any) -> dict[str, Any]:
        return _guarded(
            self.name,
            lambda: self.hand.click(
                _require_text(arguments, "window_id"),
                _require_text(arguments, "element_id"),
            ),
        )


class DesktopTypeTool(_DesktopTool):
    name = "desktop.type"
    description = "向一个可编辑元素输入文本（剪贴板优先，中文可靠）"
    risk_level = RiskLevel.HIGH
    requires_approval = True
    schema = {
        "type": "object",
        "properties": {
            "window_id": {"type": "string", "description": "driver 返回的窗口 id"},
            "element_id": {"type": "string", "description": "desktop.observe 返回的元素 id"},
            "text": {"type": "string", "description": "要输入的文本"},
        },
        "required": ["window_id", "element_id", "text"],
    }
    idempotency = "AT_MOST_ONCE"

    def execute(self, **arguments: Any) -> dict[str, Any]:
        text = arguments.get("text")
        if not isinstance(text, str):
            return {"ok": False, "action": self.name, "error": "text 必须是字符串"}
        return _guarded(
            self.name,
            lambda: self.hand.type_text(
                _require_text(arguments, "window_id"),
                _require_text(arguments, "element_id"),
                text,
            ),
        )


class DesktopKeyTool(_DesktopTool):
    name = "desktop.key"
    description = "发送一个白名单按键（如 enter / tab / ctrl+s，禁止 Win 组合）"
    risk_level = RiskLevel.HIGH
    requires_approval = True
    schema = {
        "type": "object",
        "properties": {
            "window_id": {"type": "string", "description": "driver 返回的窗口 id"},
            "key": {"type": "string", "description": "白名单键位，如 enter / tab / ctrl+s"},
        },
        "required": ["window_id", "key"],
    }
    idempotency = "AT_MOST_ONCE"

    def execute(self, **arguments: Any) -> dict[str, Any]:
        return _guarded(
            self.name,
            lambda: self.hand.press_key(
                _require_text(arguments, "window_id"),
                _require_text(arguments, "key"),
            ),
        )


class DesktopStatusTool(_DesktopTool):
    name = "desktop.status"
    description = "查询桌面手状态：驱动可用性 + 输入组开关 + 预算 / 急停"
    deadline_ms = 5_000
    schema = {"type": "object", "properties": {}}

    def execute(self, **arguments: Any) -> dict[str, Any]:
        return _guarded(self.name, self.hand.status)


DESKTOP_TOOL_CLASSES: tuple[type[_DesktopTool], ...] = (
    DesktopObserveTool,
    DesktopFocusWindowTool,
    DesktopClickTool,
    DesktopTypeTool,
    DesktopKeyTool,
    DesktopStatusTool,
)


def build_desktop_tools(
    hand: DesktopHand,
    *,
    enabled: bool = True,
) -> list[_DesktopTool]:
    """构造六个 desktop.* 工具。

    `enabled=False` 时仍构造（registry 需要能拿到 definition），
    但把 definition.implementation_status 设为 UNAVAILABLE——
    planner 的 catalog 会给它们标 `(不可用)`，LLM 一眼能看见。
    """
    status = ImplementationStatus.REAL if enabled else ImplementationStatus.UNAVAILABLE
    tools: list[_DesktopTool] = []
    for tool_class in DESKTOP_TOOL_CLASSES:
        tool = tool_class(hand)
        tool.definition.implementation_status = status
        tools.append(tool)
    return tools


__all__ = [
    "DesktopHand",
    "DesktopObserveTool",
    "DesktopFocusWindowTool",
    "DesktopClickTool",
    "DesktopTypeTool",
    "DesktopKeyTool",
    "DesktopStatusTool",
    "DESKTOP_TOOL_CLASSES",
    "build_desktop_tools",
]
