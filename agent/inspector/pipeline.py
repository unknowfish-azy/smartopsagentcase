"""
Inspector Pipeline。

组合四级纠察：

    Rule Inspector（Level 1）
    Evidence Inspector（Level 2）
    AI Judge（Level 3）
    Verifier（Level 4）

并将发现聚合成统一的 InspectionResult。
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from agent.inspector.enums import (
    InspectionCategory,
    InspectionStatus,
    InspectorTarget,
    Severity,
)
from agent.inspector.judges.ai_judge import AIJudge
from agent.inspector.judges.base import Judge
from agent.inspector.judges.evidence_judge import EvidenceJudge
from agent.inspector.judges.rule_judge import RuleJudge
from agent.inspector.models import (
    EvidenceItem,
    InspectionResult,
    InspectorIssue,
    ToolCallRecord,
)
from agent.inspector.verifiers.state_verifier import StateVerifier

_SEVERITY_ORDER = {
    Severity.INFO: 0,
    Severity.NOTICE: 1,
    Severity.WARNING: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def _max_severity(issues: list[InspectorIssue]) -> Severity:
    if not issues:
        return Severity.INFO

    return max(
        issues,
        key=lambda i: _SEVERITY_ORDER[i.severity],
    ).severity


def _highest_issue(issues: list[InspectorIssue]) -> InspectorIssue | None:
    if not issues:
        return None

    return max(
        issues,
        key=lambda i: _SEVERITY_ORDER[i.severity],
    )


class InspectorPipeline:
    """四级纠察流水线。"""

    def __init__(
        self,
        *,
        rule_judge: Judge | None = None,
        evidence_judge: Judge | None = None,
        ai_judge: Judge | None = None,
        state_verifier: StateVerifier | None = None,
    ) -> None:
        self.rule_judge = rule_judge or RuleJudge()
        self.evidence_judge = evidence_judge or EvidenceJudge()
        self.ai_judge = ai_judge or AIJudge()
        self.state_verifier = state_verifier or StateVerifier()

    def run(self, context: dict[str, Any]) -> InspectionResult:
        issues: list[InspectorIssue] = []

        issues.extend(self.rule_judge.check(context))
        issues.extend(self.evidence_judge.check(context))
        issues.extend(self.ai_judge.check(context))

        verification_result = self.state_verifier.verify(
            context.get("agent_claim"),
            context.get("actual_state"),
        )

        issues.extend(self.state_verifier.check(context))

        return self._aggregate(context, issues, verification_result)

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    def _aggregate(
        self,
        context: dict[str, Any],
        issues: list[InspectorIssue],
        verification_result: dict[str, Any],
    ) -> InspectionResult:
        agent_claim = context.get("agent_claim")
        evidence: list[EvidenceItem] = context.get("evidence") or []

        severity = _max_severity(issues)

        false_success = bool(
            verification_result.get("false_success")
        )

        if false_success:
            # 验证失败是决定性的：Agent 声称已解决但实际未解决。
            status = InspectionStatus.REJECTED
            category = InspectionCategory.VERIFICATION
            reason = verification_result["reason"]
            recommendation = (
                "验证失败，触发 Re-plan，"
                "重新分析并再次验证"
            )
        elif severity in {
            Severity.HIGH,
            Severity.CRITICAL,
        }:
            status = InspectionStatus.VIOLATION
            top = _highest_issue(issues)
            category = top.category
            reason = top.reason
            recommendation = top.recommendation
        elif issues:
            status = InspectionStatus.WARN
            top = _highest_issue(issues)
            category = top.category
            reason = top.reason
            recommendation = top.recommendation
        else:
            status = InspectionStatus.PASS
            category = None
            reason = "全部检查通过"
            recommendation = ""

        requires_human = (
            status
            in {
                InspectionStatus.VIOLATION,
                InspectionStatus.REJECTED,
            }
        ) or (
            severity
            in {
                Severity.HIGH,
                Severity.CRITICAL,
            }
        )

        return InspectionResult(
            inspection_id=(
                "INS-"
                + uuid4().hex[:12].upper()
            ),
            task_id=str(context.get("task_id", "")),
            target=InspectorTarget(
                context.get("target", "AGENT")
            ),
            status=status,
            severity=severity,
            category=category,
            agent_claim=agent_claim,
            actual_evidence=[
                item.content for item in evidence
            ],
            reason=reason,
            recommendation=recommendation,
            requires_human=requires_human,
            issues=issues,
            evidence_label=(
                EvidenceJudge.evaluate_evidence(
                    agent_claim,
                    evidence,
                )["label"]
                if evidence or agent_claim
                else None
            ),
            policy_result={
                "tool_calls": len(
                    context.get("tool_calls") or []
                )
            },
            evidence_result=EvidenceJudge.evaluate_evidence(
                agent_claim,
                evidence,
            ),
            verification_result=verification_result,
            metadata=context.get("metadata") or {},
        )


__all__ = [
    "InspectorPipeline",
]
