"""
State Verifier（Level 4）。

不直接相信 Agent 的「问题已解决」结论，
而是用实际系统状态与之对比。

    Agent Claim：「故障已解决」
    Actual State：502 仍存在
    => FALSE_SUCCESS / REJECTED
"""

from __future__ import annotations

from typing import Any

from agent.inspector.enums import InspectionCategory, Severity
from agent.inspector.models import InspectorIssue

_RESOLVED_PATTERNS = (
    "已解决",
    "已恢复",
    "恢复正常",
    "解决",
    "恢复",
    "resolved",
    "fixed",
    "recovered",
    "ok",
)


def claims_resolved(agent_claim: str | None) -> bool:
    if not agent_claim:
        return False

    text = agent_claim.lower()

    return any(
        pattern in text
        for pattern in _RESOLVED_PATTERNS
    )


class StateVerifier:
    """
    根据实际系统状态验证 Agent 结论。

    actual_state 形如：

        {"resolved": False, "status": "502", "detail": "..."}
    """

    def verify(
        self,
        agent_claim: str | None,
        actual_state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not agent_claim or not actual_state:
            return {
                "checked": False,
                "passed": None,
                "reason": "缺少结论或实际状态，跳过验证",
            }

        resolved_claim = claims_resolved(agent_claim)

        actual_resolved = bool(
            actual_state.get("resolved", False)
        )

        if resolved_claim and not actual_resolved:
            return {
                "checked": True,
                "passed": False,
                "false_success": True,
                "reason": (
                    "Agent 声称已解决，但实际状态仍异常："
                    f"{actual_state.get('status', actual_state)}"
                ),
            }

        return {
            "checked": True,
            "passed": True,
            "false_success": False,
            "reason": "结论与实际状态一致",
        }

    def check(self, context: dict[str, Any]) -> list[InspectorIssue]:
        result = self.verify(
            context.get("agent_claim"),
            context.get("actual_state"),
        )

        if result.get("false_success"):
            return [
                InspectorIssue(
                    category=InspectionCategory.VERIFICATION,
                    severity=Severity.HIGH,
                    reason=result["reason"],
                    recommendation=(
                        "验证失败，触发 Re-plan，"
                        "重新分析并再次验证"
                    ),
                )
            ]

        return []


__all__ = [
    "StateVerifier",
    "claims_resolved",
]
