"""
SmartOps Inspector 数据模型。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.inspector.enums import (
    EvidenceLabel,
    InspectionCategory,
    InspectionStatus,
    InspectorTarget,
    Severity,
)


@dataclass
class EvidenceItem:
    """一条证据。"""

    content: str
    source: str = ""
    version: str = "latest"
    score: float = 0.0


@dataclass
class ToolCallRecord:
    """一次工具调用记录（Agent 声称的风险 / 审批 / 结果）。"""

    tool_name: str
    risk: str = "LOW"
    approval_granted: bool = False
    success: bool = False
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class InspectorIssue:
    """单条纠察发现。"""

    category: InspectionCategory
    severity: Severity
    reason: str
    recommendation: str = ""


@dataclass
class InspectionResult:
    """一次纠察的最终结果。"""

    inspection_id: str
    task_id: str
    target: InspectorTarget

    status: InspectionStatus
    severity: Severity

    category: InspectionCategory | None

    agent_claim: str | None

    actual_evidence: list[str]

    reason: str

    recommendation: str

    requires_human: bool

    issues: list[InspectorIssue] = field(default_factory=list)

    evidence_label: EvidenceLabel | None = None

    policy_result: dict[str, Any] | None = None
    evidence_result: dict[str, Any] | None = None
    verification_result: dict[str, Any] | None = None

    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "inspection_id": self.inspection_id,
            "task_id": self.task_id,
            "target": self.target.value,
            "status": self.status.value,
            "severity": self.severity.value,
            "category": (
                self.category.value
                if self.category
                else None
            ),
            "agent_claim": self.agent_claim,
            "actual_evidence": self.actual_evidence,
            "reason": self.reason,
            "recommendation": self.recommendation,
            "requires_human": self.requires_human,
            "issues": [
                {
                    "category": issue.category.value,
                    "severity": issue.severity.value,
                    "reason": issue.reason,
                    "recommendation": issue.recommendation,
                }
                for issue in self.issues
            ],
            "evidence_label": (
                self.evidence_label.value
                if self.evidence_label
                else None
            ),
            "policy_result": self.policy_result,
            "evidence_result": self.evidence_result,
            "verification_result": self.verification_result,
            "metadata": self.metadata,
        }


__all__ = [
    "EvidenceItem",
    "ToolCallRecord",
    "InspectorIssue",
    "InspectionResult",
]
