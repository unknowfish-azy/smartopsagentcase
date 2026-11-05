"""
Trace Collector。

监听 Agent EventBus，将执行轨迹（工具调用、审批、验证）聚合为
Inspector 可直接消费的上下文。

事件 payload 约定：

    tool.before_call / tool.after_call
        {
            "request_id": "...",
            "tool_name": "nginx.status",
            "risk": "LOW",
            "approval_granted": false,
            "success": true,
            "args": {}
        }

    approval.required / granted / denied
        {"request_id": "...", "operation": "nginx.restart"}

    verification.finished
        {"request_id": "...", "probes": [{"type": "http", "status_code": 502}]}
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from agent.inspector.models import ToolCallRecord
from agent.kernel.event.bus import EventBus
from agent.kernel.event.events import (
    APPROVAL_DENIED,
    APPROVAL_GRANTED,
    APPROVAL_REQUIRED,
    TOOL_AFTER_CALL,
    TOOL_BEFORE_CALL,
    VERIFICATION_FINISHED,
    AgentEvent,
)

_EVENTS = (
    TOOL_BEFORE_CALL,
    TOOL_AFTER_CALL,
    APPROVAL_REQUIRED,
    APPROVAL_GRANTED,
    APPROVAL_DENIED,
    VERIFICATION_FINISHED,
)


class TraceCollector:
    """按 request_id 聚合执行轨迹。"""

    def __init__(self) -> None:
        self._tool_calls: dict[str, list[ToolCallRecord]] = (
            defaultdict(list)
        )
        self._approvals: dict[str, set[str]] = defaultdict(set)
        self._denials: dict[str, set[str]] = defaultdict(set)
        self._actual_state: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # EventBus
    # ------------------------------------------------------------------

    def subscribe(self, bus: EventBus) -> "TraceCollector":
        for name in _EVENTS:
            bus.subscribe(name, self.on_event)

        return self

    async def on_event(self, event: AgentEvent) -> None:
        payload = event.payload or {}

        request_id = (
            event.request_id
            or payload.get("request_id")
        )

        if not request_id:
            return

        # 仅在 tool.after_call 时记录已完成调用，
        # 避免 before/after 重复计入同一调用。
        if event.name == TOOL_AFTER_CALL:
            tool_name = payload.get("tool_name")

            if not tool_name:
                return

            self._tool_calls[request_id].append(
                ToolCallRecord(
                    tool_name=str(tool_name),
                    risk=str(
                        payload.get("risk", "LOW")
                    ).upper(),
                    approval_granted=bool(
                        payload.get("approval_granted")
                    ),
                    success=bool(
                        payload.get("success")
                    ),
                    args=payload.get("args") or {},
                )
            )

        elif event.name == APPROVAL_GRANTED:
            operation = payload.get(
                "operation"
            ) or payload.get("tool_name")

            if operation:
                self._approvals[request_id].add(
                    str(operation)
                )

        elif event.name == APPROVAL_DENIED:
            operation = payload.get(
                "operation"
            ) or payload.get("tool_name")

            if operation:
                self._denials[request_id].add(
                    str(operation)
                )

        elif event.name == VERIFICATION_FINISHED:
            self._actual_state[request_id] = {
                "probes": payload.get("probes") or [],
                "observed_at": payload.get("observed_at"),
            }

    # ------------------------------------------------------------------
    # Trace access
    # ------------------------------------------------------------------

    def tool_calls(
        self,
        request_id: str,
    ) -> list[ToolCallRecord]:
        calls = list(
            self._tool_calls.get(request_id, [])
        )

        approved = self._approvals.get(
            request_id,
            set(),
        )

        for call in calls:
            if call.tool_name in approved:
                call.approval_granted = True

        return calls

    def actual_state(
        self,
        request_id: str,
    ) -> dict[str, Any] | None:
        return self._actual_state.get(request_id)

    def build_context(
        self,
        request_id: str,
        *,
        target: str = "AGENT",
        agent_claim: str | None = None,
        evidence: list[Any] | None = None,
        policy: dict[str, Any] | None = None,
        environment_version: str | None = None,
    ) -> dict[str, Any]:
        """构建 Inspector 可直接消费的上下文。"""
        return {
            "task_id": request_id,
            "target": target,
            "agent_claim": agent_claim,
            "evidence": evidence or [],
            "tool_calls": self.tool_calls(request_id),
            "policy": policy or {},
            "environment_version": environment_version,
            "actual_state": self.actual_state(request_id),
        }

    def clear(self, request_id: str | None = None) -> None:
        if request_id is None:
            self._tool_calls.clear()
            self._approvals.clear()
            self._denials.clear()
            self._actual_state.clear()
            return

        self._tool_calls.pop(request_id, None)
        self._approvals.pop(request_id, None)
        self._denials.pop(request_id, None)
        self._actual_state.pop(request_id, None)


__all__ = [
    "TraceCollector",
]
