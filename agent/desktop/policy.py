"""DH-02 门禁策略配置。

R1（禁点确认 / 同意 / 支付类元素）与 R2（禁入 cmd / regedit / taskmgr 等窗口）
是模块级硬编码常量，**没有配置开关**，见 ARCHITECTURE §4。

其余项（输入组开关、窗口白名单、动作预算、限速、重复点击上限）可配置，
但只能收紧不能放大 R1 / R2。

本模块平台无关，不得 import 任何系统控制库。
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# R2 禁入区（硬编码，不可配）
# ---------------------------------------------------------------------------

FORBIDDEN_PROCESSES = frozenset(
    {
        "cmd",
        "powershell",
        "pwsh",
        "regedit",
        "taskmgr",
        "mmc",
        "control",
        "msconfig",
        "gpedit",
    }
)

FORBIDDEN_TITLE_KEYWORDS = (
    "cmd",
    "powershell",
    "pwsh",
    "terminal",
    "regedit",
    "taskmgr",
    "mmc",
    "msconfig",
    "gpedit",
    "命令提示符",
    "控制面板",
    "注册表编辑器",
    "任务管理器",
)

# ---------------------------------------------------------------------------
# R1 代签禁令（硬编码，不可配）
# ---------------------------------------------------------------------------

DESTRUCTIVE_TEXT = (
    # 中文：确认类文案
    "同意",
    "确认",
    "确定",
    "允许",
    "授权",
    "支付",
    "付款",
    "转账",
    "签署",
    "签订",
    "提交订单",
    "删除",
    "卸载",
    "格式化",
    # 英文：同一批语义（小写比对）
    "confirm",
    "agree",
    "accept",
    "authorize",
    "authorise",
    "pay",
    "purchase",
    "sign",
    "delete",
    "remove",
    "uninstall",
    "format",
    "submit order",
)


def matches_destructive_text(name: str) -> bool:
    """元素可读名是否命中代签类文案（子串匹配，fail-closed）。"""

    if not name:
        return False

    normalized = name.strip().lower()
    if not normalized:
        return False

    return any(keyword in normalized for keyword in DESTRUCTIVE_TEXT)


# ---------------------------------------------------------------------------
# 窗口白名单（R3）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WindowRule:
    """一条白名单：进程名 + 标题正则 + 允许的元素角色。

    allowed_roles 为空表示「不允许任何元素角色」，即只能 observe / focus_window。
    必须显式登记角色才能点击（ARCHITECTURE §4 R3）。
    """

    process: str
    title_regex: str
    allowed_roles: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not self.process or not self.process.strip():
            raise ValueError("WindowRule.process 不能为空")

        # 构造期即编译，坏正则直接炸，不留到运行期。
        re.compile(self.title_regex)

        roles = self.allowed_roles
        if isinstance(roles, (list, tuple, set)):
            roles = frozenset(roles)
        if not isinstance(roles, frozenset):
            raise ValueError("WindowRule.allowed_roles 必须是字符串集合")
        for role in roles:
            if not isinstance(role, str) or not role:
                raise ValueError("WindowRule.allowed_roles 只允许非空字符串")

        object.__setattr__(self, "allowed_roles", roles)

    def normalized_process(self) -> str:
        return normalize_process_name(self.process)


def normalize_process_name(process_name: str) -> str:
    """进程名归一：去路径、去 .exe、小写、去空白。"""

    value = (process_name or "").strip().lower()
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    if value.endswith(".exe"):
        value = value[: -len(".exe")]
    return value


# ---------------------------------------------------------------------------
# 策略
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesktopPolicy:
    """默认姿态：输入组关闭、白名单为空（全部拒绝）、50 步预算。"""

    input_group_enabled: bool = False
    window_allowlist: tuple[WindowRule, ...] = ()
    step_budget: int = 50
    min_interval_ms: int = 300
    same_element_streak_limit: int = 3

    def __post_init__(self) -> None:
        if not isinstance(self.input_group_enabled, bool):
            raise ValueError("input_group_enabled 必须是 bool")

        rules = self.window_allowlist
        if isinstance(rules, list):
            rules = tuple(rules)
        if not isinstance(rules, tuple):
            raise ValueError("window_allowlist 必须是 WindowRule 序列")
        for rule in rules:
            if not isinstance(rule, WindowRule):
                raise ValueError("window_allowlist 只允许 WindowRule")
        object.__setattr__(self, "window_allowlist", rules)

        for name in ("step_budget", "min_interval_ms", "same_element_streak_limit"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} 必须是整数")
            if value < 0:
                raise ValueError(f"{name} 不能为负")

        if self.step_budget < 1:
            raise ValueError("step_budget 至少为 1")

        if self.same_element_streak_limit < 1:
            raise ValueError("same_element_streak_limit 至少为 1")

    @classmethod
    def from_env(cls) -> "DesktopPolicy":
        """从环境变量装配策略。默认值全安全：输入组关、白名单空。

        变量名两种都支持：ARCHITECTURE §4 写的 `DESKTOP_HAND_*` 优先，
        没设再查项目惯例的 `SMARTOPS_DESKTOP_HAND_*`。
        """
        value = _env_flag("DESKTOP_HAND_INPUT_GROUP", "SMARTOPS_DESKTOP_HAND_INPUT_GROUP")
        return cls(input_group_enabled=value)


def desktop_hand_enabled() -> bool:
    """总开关：`DESKTOP_HAND_ENABLED` / `SMARTOPS_DESKTOP_HAND_ENABLED`。

    **默认 false**——没显式开启就认为桌面手不可用，registry 装配时会把
    所有 desktop.* 工具标成 UNAVAILABLE。这是 ARCHITECTURE §4 的核心姿态：
    UI 是兜底，默认不注册就不会被 LLM 看到。
    """
    return _env_flag("DESKTOP_HAND_ENABLED", "SMARTOPS_DESKTOP_HAND_ENABLED", default=False)


def _env_flag(*names: str, default: bool = False) -> bool:
    """顺序查环境变量，第一个有值就返回；都没值用 default。"""
    for name in names:
        raw = os.getenv(name)
        if raw is None:
            continue
        value = raw.strip().lower()
        if value in {"", "0", "false", "no", "off"}:
            return False
        return True
    return default
