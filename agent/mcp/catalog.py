"""
SmartOps MCP 工具目录（暴露面控制）。

MCP server 暴露哪些工具，由本目录决定，**默认保守**：

    * 显式 allowlist（环境变量 / 构造参数）优先，可暴露任意工具；
    * 未配置 allowlist 时，只暴露同时满足以下条件的工具：
        - `implementation_status == REAL`（不是模板/不可用）
        - `risk in {LOW, MEDIUM}`
        - `idempotency == SAFE_RETRY`（只读、可安全重试）
    * 没有 `definition` 的旧式工具一律不暴露（无法判定风险与 schema）。

安全边界：目录只决定"能不能被 MCP 看见"，**不绕过**执行链的
Permission / Risk / Approval / SafeAgent / Sandbox / Verification / Audit——
真正执行仍走 `AgentExecutor`。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from agent.policies.risk import RiskLevel
from agent.sdk.tool import ImplementationStatus, PluginTool


# 默认允许暴露的风险上限（不含 HIGH / CRITICAL）。
_DEFAULT_MAX_RISK = RiskLevel.MEDIUM


@dataclass(frozen=True)
class CatalogEntry:
    """目录中的一项工具。"""

    name: str
    description: str
    input_schema: dict[str, Any]
    risk: RiskLevel
    idempotency: str
    implementation_status: ImplementationStatus
    tool: PluginTool


class ToolCatalog:
    """MCP 工具目录。"""

    def __init__(
        self,
        entries: Iterable[CatalogEntry],
    ) -> None:
        self._entries: dict[str, CatalogEntry] = {
            entry.name: entry
            for entry in entries
        }

    def __len__(self) -> int:
        return len(self._entries)

    def get(
        self,
        name: str,
    ) -> CatalogEntry | None:
        return self._entries.get(name)

    def list_entries(self) -> list[CatalogEntry]:
        return sorted(
            self._entries.values(),
            key=lambda entry: entry.name,
        )

    def list_tools(self) -> list[dict[str, Any]]:
        """输出 MCP `tools/list` 的 Tool 对象数组。"""

        tools: list[dict[str, Any]] = []

        for entry in self.list_entries():
            tools.append(
                {
                    "name": entry.name,
                    "description": entry.description,
                    "inputSchema": entry.input_schema
                    or {
                        "type": "object",
                        "properties": {},
                    },
                }
            )

        return tools

    # ------------------------------------------------------------------

    @classmethod
    def from_registry(
        cls,
        registry,
        *,
        allowlist: Iterable[str] | None = None,
    ) -> "ToolCatalog":
        """从 `agent.registry.ToolRegistry` 构建目录。

        allowlist 非空时按其暴露（仍要求工具是 PluginTool）；
        为空时按默认只读策略过滤。
        """

        allowed = _normalize_allowlist(allowlist)

        entries: list[CatalogEntry] = []

        for tool in registry.list():
            entry = _to_entry(tool)

            if entry is None:
                continue

            if allowed is not None:
                if entry.name in allowed:
                    entries.append(entry)
                continue

            if _passes_default_policy(entry):
                entries.append(entry)

        return cls(entries)

    @classmethod
    def empty(cls) -> "ToolCatalog":
        return cls(())


def _normalize_allowlist(
    allowlist: Iterable[str] | None,
) -> set[str] | None:
    if allowlist is None:
        return None

    normalized = {
        str(name).strip()
        for name in allowlist
        if str(name).strip()
    }

    return normalized or None


def _to_entry(tool: Any) -> CatalogEntry | None:
    """把 PluginTool 转成目录项；不支持的工具返回 None。"""

    if not isinstance(tool, PluginTool):
        return None

    definition = getattr(tool, "definition", None)

    if definition is None:
        return None

    status = getattr(
        definition,
        "implementation_status",
        ImplementationStatus.REAL,
    )

    return CatalogEntry(
        name=str(definition.name),
        description=str(
            getattr(definition, "description", "")
            or ""
        ),
        input_schema=dict(
            getattr(definition, "input_schema", {})
            or {}
        ),
        risk=getattr(
            definition,
            "risk",
            RiskLevel.LOW,
        ),
        idempotency=str(
            getattr(definition, "idempotency", "SAFE_RETRY")
        ),
        implementation_status=status,
        tool=tool,
    )


def _passes_default_policy(
    entry: CatalogEntry,
) -> bool:
    """默认只读策略：REAL + 风险 ≤ MEDIUM + 可安全重试。"""

    if entry.implementation_status != ImplementationStatus.REAL:
        return False

    if entry.risk not in (
        RiskLevel.LOW,
        _DEFAULT_MAX_RISK,
    ):
        return False

    return entry.idempotency == "SAFE_RETRY"


__all__ = [
    "CatalogEntry",
    "ToolCatalog",
]
