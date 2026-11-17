"""护栏策略配置：统一从 Settings 读取，集中暴露运行时开关。

配置项（DESIGN §4⑥ / D2-D4 裁决默认值）：
- guard_enabled        总开关。False 时所有检查直接放行（审计记 GUARD_DISABLED 计数）。
- guard_fail_closed    护栏自身异常时拒绝（True，D 裁决默认）。
- guard_stream_enabled 流式滑动窗口截断（False，W4 默认关闭，离线验证后再开）。
"""

from __future__ import annotations

import logging

from ..core.config import settings
from .contract import ALLOW, GuardDecision

logger = logging.getLogger(__name__)


def guard_enabled() -> bool:
    return bool(getattr(settings, "guard_enabled", True))


def fail_closed() -> bool:
    return bool(getattr(settings, "guard_fail_closed", True))


def stream_enabled() -> bool:
    return bool(getattr(settings, "guard_stream_enabled", False))


def rule_version() -> str:
    return str(getattr(settings, "guard_rule_version", "1.0.0"))


def bypass() -> GuardDecision:
    """总开关关闭时的统一放行结果。"""
    return ALLOW
