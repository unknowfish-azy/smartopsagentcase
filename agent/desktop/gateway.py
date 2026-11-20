"""DH-02 网关：唯一允许做策略判断的地方（ARCHITECTURE §3 铁律 2）。

检查顺序固定，命中即返回（顺序固定是为了回归可判定：同输入必得同一 reject_reason）：

    R6 观测完整性 → R5 急停锁 → R4 预算 / 限速 / 重复点击
    → R2 禁入区 → R3 窗口白名单 → R1 危险元素文案 → 输入组开关

R1 / R2 没有配置开关；急停只能由人恢复（resume 需要 emergency_stop 产出的一次性 token，
Agent 侧拿不到 token）。

本模块平台无关，不得 import 任何系统控制库。
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass
from typing import Any, Mapping

from agent.desktop.models import (
    DesktopContractError,
    TARGET_KEYS,
    UiObservation,
    WindowInfo,
)
from agent.desktop.policy import (
    FORBIDDEN_PROCESSES,
    FORBIDDEN_TITLE_KEYWORDS,
    DesktopPolicy,
    WindowRule,
    matches_destructive_text,
    normalize_process_name,
)

INPUT_ACTIONS = frozenset({"click", "type", "key"})
ELEMENT_ACTIONS = frozenset({"click", "type"})
KNOWN_ACTIONS = frozenset({"observe", "focus_window"}) | INPUT_ACTIONS

# desktop.key 白名单。不含任何 Win / Meta 组合（R2 逃逸通道）。
ALLOWED_KEYS = frozenset(
    {
        "enter",
        "tab",
        "escape",
        "space",
        "backspace",
        "delete",
        "up",
        "down",
        "left",
        "right",
        "home",
        "end",
        "pageup",
        "pagedown",
        "ctrl+a",
        "ctrl+c",
        "ctrl+v",
        "ctrl+x",
        "ctrl+z",
        "ctrl+s",
        "ctrl+f",
        "ctrl+w",
    }
)


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reject_reason: str | None = None
    needs_approval: bool = False


class DesktopGateway:
    """有状态门禁。一个实例 = 一个会话（预算 / 限速 / 急停都在实例内）。"""

    def __init__(
        self,
        policy: DesktopPolicy | None = None,
        *,
        enabled: bool = True,
    ) -> None:
        self._policy = policy or DesktopPolicy()
        self._enabled = enabled
        self._steps = 0
        self._last_action_at: float | None = None
        self._last_element_key: tuple[str, str] | None = None
        self._same_element_streak = 0
        self._stopped = False
        self._stop_reason: str | None = None
        self._resume_token: str | None = None

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def authorize(
        self,
        action: str,
        target: Mapping[str, Any],
        obs: UiObservation | None = None,
        *,
        window: WindowInfo | None = None,
        key: str | None = None,
        now: float | None = None,
    ) -> Decision:
        """判定一次动作是否放行。

        放行时会推进预算与重复计数，因此每个动作只应调用一次。
        """

        if action not in KNOWN_ACTIONS:
            raise DesktopContractError(f"未知动作: {action!r}")

        # 总开关关：整个桌面手对 Agent 不可用，比 R5 更硬——不是"急停"是"根本没装上"
        if not self._enabled:
            return Decision(allowed=False, reject_reason="TOTAL_DISABLED")

        target = self._validate_target(action, target)
        moment = time.monotonic() if now is None else float(now)
        resolved_window = self._resolve_window(obs, window)

        for check in (
            lambda: self._check_r6(action, target, obs),
            lambda: self._check_r5(),
            lambda: self._check_r4(action, target, moment),
            lambda: self._check_r2(action, resolved_window, key),
            lambda: self._check_r3(action, target, resolved_window, obs),
            lambda: self._check_r1(action, target, obs),
            lambda: self._check_input_group(action),
        ):
            decision = check()
            if decision is not None:
                return decision

        self._record(action, target, moment)
        return Decision(
            allowed=True,
            needs_approval=action in INPUT_ACTIONS,
        )

    # ------------------------------------------------------------------
    # R6 观测完整性
    # ------------------------------------------------------------------

    def _check_r6(
        self,
        action: str,
        target: Mapping[str, Any],
        obs: UiObservation | None,
    ) -> Decision | None:
        if action not in INPUT_ACTIONS:
            return None

        if obs is None:
            return Decision(False, "R6_NO_OBSERVATION")

        if obs.truncated:
            return Decision(False, "R6_TRUNCATED")

        if obs.window_id != target["window_id"]:
            return Decision(False, "R6_WINDOW_MISMATCH")

        if action in ELEMENT_ACTIONS and obs.find_element(target["element_id"]) is None:
            return Decision(False, "R6_ELEMENT_UNKNOWN")

        return None

    # ------------------------------------------------------------------
    # R5 急停
    # ------------------------------------------------------------------

    def _check_r5(self) -> Decision | None:
        if self._stopped:
            return Decision(False, "R5_STOPPED")
        return None

    def emergency_stop(self, reason: str) -> str:
        """置急停锁，返回一次性人工恢复 token。

        token 只应展示给现场操作者（热键处理器 / 审计日志），不得进入任何 Agent 工具。
        """

        self._stopped = True
        self._stop_reason = reason
        self._resume_token = secrets.token_hex(8)
        return self._resume_token

    def resume(self, human_token: str | None = None) -> Decision:
        """仅人类入口可调用。Agent 侧无 token，一律 R5_AGENT_CANNOT_RESUME。"""

        if not self._stopped:
            return Decision(True)

        if not human_token or human_token != self._resume_token:
            return Decision(False, "R5_AGENT_CANNOT_RESUME")

        self._stopped = False
        self._stop_reason = None
        self._resume_token = None
        return Decision(True)

    # ------------------------------------------------------------------
    # R4 预算 / 限速 / 重复点击
    # ------------------------------------------------------------------

    def _check_r4(
        self,
        action: str,
        target: Mapping[str, Any],
        moment: float,
    ) -> Decision | None:
        policy = self._policy

        if self._steps >= policy.step_budget:
            return Decision(False, "R4_BUDGET")

        if (
            policy.min_interval_ms > 0
            and self._last_action_at is not None
            and (moment - self._last_action_at) * 1000.0 < policy.min_interval_ms
        ):
            return Decision(False, "R4_RATE")

        streak_key = self._streak_key(action, target)
        if (
            streak_key is not None
            and streak_key == self._last_element_key
            and self._same_element_streak >= policy.same_element_streak_limit
        ):
            return Decision(False, "R4_REPEAT")

        return None

    # ------------------------------------------------------------------
    # R2 禁入区
    # ------------------------------------------------------------------

    def _check_r2(
        self,
        action: str,
        window: WindowInfo | None,
        key: str | None,
    ) -> Decision | None:
        if action == "key":
            if key is None:
                return Decision(False, "R2_FORBIDDEN_KEY")
            if self._normalize_key(key) not in ALLOWED_KEYS:
                return Decision(False, "R2_FORBIDDEN_KEY")

        if window is None:
            return None

        if normalize_process_name(window.process_name) in FORBIDDEN_PROCESSES:
            return Decision(False, "R2_FORBIDDEN_PROCESS")

        title = (window.window_title or "").lower()
        if any(keyword in title for keyword in FORBIDDEN_TITLE_KEYWORDS):
            return Decision(False, "R2_FORBIDDEN_WINDOW")

        return None

    # ------------------------------------------------------------------
    # R3 窗口白名单
    # ------------------------------------------------------------------

    def _check_r3(
        self,
        action: str,
        target: Mapping[str, Any],
        window: WindowInfo | None,
        obs: UiObservation | None,
    ) -> Decision | None:
        if window is None:
            return Decision(False, "R3_NO_WINDOW")

        rule = self._match_rule(window)
        if rule is None:
            return Decision(False, "R3_WINDOW_NOT_ALLOWED")

        if action in ELEMENT_ACTIONS:
            element = obs.find_element(target["element_id"]) if obs else None
            if element is None:
                return Decision(False, "R6_ELEMENT_UNKNOWN")
            if element.role not in rule.allowed_roles:
                return Decision(False, "R3_ROLE_NOT_ALLOWED")

        return None

    # ------------------------------------------------------------------
    # R1 代签禁令
    # ------------------------------------------------------------------

    def _check_r1(
        self,
        action: str,
        target: Mapping[str, Any],
        obs: UiObservation | None,
    ) -> Decision | None:
        if action not in ELEMENT_ACTIONS:
            return None

        element = obs.find_element(target["element_id"]) if obs else None
        if element is None:
            return Decision(False, "R6_ELEMENT_UNKNOWN")

        if element.is_destructive or matches_destructive_text(element.name):
            return Decision(False, "R1_DESTRUCTIVE_ELEMENT")

        return None

    # ------------------------------------------------------------------
    # 输入组开关
    # ------------------------------------------------------------------

    def _check_input_group(self, action: str) -> Decision | None:
        if action in INPUT_ACTIONS and not self._policy.input_group_enabled:
            return Decision(False, "INPUT_GROUP_DISABLED")
        return None

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "input_group_enabled": self._policy.input_group_enabled,
            "stopped": self._stopped,
            "stop_reason": self._stop_reason,
            "steps": self._steps,
            "step_budget": self._policy.step_budget,
            "same_element_streak": self._same_element_streak,
            "allowlist_size": len(self._policy.window_allowlist),
            # R1 / R2 没有开关，这里写死给运维看。
            "r1_destructive_guard": "ALWAYS_ON",
            "r2_forbidden_window_guard": "ALWAYS_ON",
        }

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_target(
        action: str,
        target: Mapping[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(target, Mapping):
            raise DesktopContractError("target 必须是映射")

        extra = set(target) - TARGET_KEYS
        if extra:
            raise DesktopContractError(
                f"target 只允许键 {sorted(TARGET_KEYS)}，出现: {sorted(extra)}"
                "——坐标一律禁止，见 ARCHITECTURE §9.1"
            )

        window_id = target.get("window_id")
        if not window_id or not isinstance(window_id, str):
            raise DesktopContractError("target.window_id 必填且必须是非空字符串")

        if action in ELEMENT_ACTIONS:
            element_id = target.get("element_id")
            if not element_id or not isinstance(element_id, str):
                raise DesktopContractError(f"{action} 需要 target.element_id")

        return dict(target)

    @staticmethod
    def _resolve_window(
        obs: UiObservation | None,
        window: WindowInfo | None,
    ) -> WindowInfo | None:
        if window is not None:
            return window
        if obs is not None:
            return obs.as_window()
        return None

    @staticmethod
    def _streak_key(
        action: str,
        target: Mapping[str, Any],
    ) -> tuple[str, str] | None:
        if action not in ELEMENT_ACTIONS:
            return None
        return (target["window_id"], target["element_id"])

    @staticmethod
    def _normalize_key(key: str) -> str:
        return key.strip().lower().replace(" ", "")

    def _match_rule(self, window: WindowInfo) -> WindowRule | None:
        process = normalize_process_name(window.process_name)

        for rule in self._policy.window_allowlist:
            if rule.normalized_process() != process:
                continue
            if re.search(rule.title_regex, window.window_title or ""):
                return rule
        return None

    def _record(
        self,
        action: str,
        target: Mapping[str, Any],
        moment: float,
    ) -> None:
        self._steps += 1
        self._last_action_at = moment

        streak_key = self._streak_key(action, target)
        if streak_key is None:
            return

        if streak_key == self._last_element_key:
            self._same_element_streak += 1
        else:
            self._last_element_key = streak_key
            self._same_element_streak = 1
