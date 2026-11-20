"""DH-07 工具路由优先级：`api > shell > desktop`。

两条纪律（与 ARCHITECTURE §2 一致）：
1. **只引导不强制**：catalog 按 API → CLI → UI 排序 + 系统提示词明确优先级，
   让 LLM 在三者都可用时自然选 API；planner 不做"自动路由"（怕把偶发超时变成乱点）。
2. **不可用要显式**：API 工具一旦 `implementation_status=UNAVAILABLE`，
   在 catalog 里标注 `(不可用)` 并自动降级到 shell 之后——**不是**"调一次报错就降级"。

分类依据（依次尝试）：
- `ToolDefinition.target_type`：`AI_SERVICE`=API，`DESKTOP`=UI，其他=CLI；
- 工具名前缀：`nn.` / `api.` → API，`shell.` → CLI，`desktop.` → UI。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Iterable

from agent.sdk.tool import ImplementationStatus

API_PREFIXES = ("nn.", "api.", "anomaly", "rootcause", "logclassify", "retrieve")
SHELL_PREFIXES = ("shell.", "bash.", "cmd.")
DESKTOP_PREFIXES = ("desktop.",)


class RouteTier(IntEnum):
    """路由层级：数值越小优先级越高。"""

    API = 0
    SHELL = 1
    UI = 2
    UNKNOWN = 3


_TIER_BY_TARGET_TYPE = {
    "AI_SERVICE": RouteTier.API,
    "DESKTOP": RouteTier.UI,
}


def classify_tool(tool) -> RouteTier:
    """按 target_type 再按前缀分类；工具没有 definition 时按名字猜。"""
    definition = getattr(tool, "definition", None)
    if definition is not None:
        tier = _TIER_BY_TARGET_TYPE.get(definition.target_type)
        if tier is not None:
            return tier

    name = getattr(tool, "name", "")
    if any(name.startswith(prefix) for prefix in API_PREFIXES):
        return RouteTier.API
    if any(name.startswith(prefix) for prefix in SHELL_PREFIXES):
        return RouteTier.SHELL
    if any(name.startswith(prefix) for prefix in DESKTOP_PREFIXES):
        return RouteTier.UI
    return RouteTier.UNKNOWN


def is_unavailable(tool) -> bool:
    """工具是否"明确不可用"（装配时就知道，不是调用报错）。"""
    definition = getattr(tool, "definition", None)
    if definition is None:
        # 旧式工具没有 ToolDefinition：假设可用（避免误杀）
        return False
    status = getattr(definition, "implementation_status", ImplementationStatus.REAL)
    return status == ImplementationStatus.UNAVAILABLE


def available_before_unavailable(tool):
    """排序 key：先按 tier，同 tier 内可用的在前、不可用的在后。"""
    tier = classify_tool(tool)
    unavailable = is_unavailable(tool)
    return (tier, unavailable, getattr(tool, "name", ""))


def sort_by_priority(tools: Iterable) -> list:
    """按 `API > CLI > UI` 排序，同 tier 内可用的在前。"""
    return sorted(tools, key=available_before_unavailable)


TIER_LABELS = {
    RouteTier.API: "API（优先）",
    RouteTier.SHELL: "CLI（次选）",
    RouteTier.UI: "UI（兜底，仅在前两者明确不可用时）",
    RouteTier.UNKNOWN: "其他",
}


__all__ = [
    "RouteTier",
    "classify_tool",
    "is_unavailable",
    "sort_by_priority",
    "TIER_LABELS",
    "API_PREFIXES",
    "SHELL_PREFIXES",
    "DESKTOP_PREFIXES",
]
