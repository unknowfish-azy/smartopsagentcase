"""
Evidence Judge（Level 2）。

证据纠察：

    - 证据不足（EVIDENCE）
    - 版本不匹配（VERSION）
    - 结论与证据一致性标签（SUPPORTED / UNSUPPORTED / ...）
"""

from __future__ import annotations

import re
from typing import Any

from agent.inspector.enums import (
    EvidenceLabel,
    InspectionCategory,
    Severity,
)
from agent.inspector.judges.base import Judge
from agent.inspector.models import EvidenceItem, InspectorIssue


def _tokens(text: str) -> set[str]:
    return set(
        re.findall(
            r"[一-鿿]+|[a-zA-Z0-9_]+",
            (text or "").lower(),
        )
    )


def label_evidence(
    agent_claim: str | None,
    evidence: list[EvidenceItem],
) -> EvidenceLabel:
    """
    判断结论是否被证据支持。

    证据优先，而不是语言模型自洽优先。
    """
    if not agent_claim or not agent_claim.strip():
        return EvidenceLabel.SUPPORTED

    if not evidence:
        return EvidenceLabel.UNSUPPORTED

    claim_tokens = _tokens(agent_claim)

    if not claim_tokens:
        return EvidenceLabel.SUPPORTED

    evidence_text = " ".join(
        item.content for item in evidence
    )

    evidence_tokens = _tokens(evidence_text)

    overlap = len(claim_tokens & evidence_tokens)
    ratio = overlap / len(claim_tokens)

    if ratio >= 0.5:
        return EvidenceLabel.SUPPORTED

    if ratio >= 0.2:
        return EvidenceLabel.PARTIALLY_SUPPORTED

    return EvidenceLabel.UNSUPPORTED


class EvidenceJudge(Judge):
    """证据纠察。"""

    def __init__(self, *, min_evidence: int = 1) -> None:
        self.min_evidence = min_evidence

    def check(self, context: dict[str, Any]) -> list[InspectorIssue]:
        issues: list[InspectorIssue] = []

        agent_claim = context.get("agent_claim")
        evidence = context.get("evidence") or []
        environment_version = context.get("environment_version")

        issues.extend(
            self._check_sufficiency(agent_claim, evidence)
        )

        issues.extend(
            self._check_version(
                evidence,
                environment_version,
            )
        )

        label = label_evidence(agent_claim, evidence)

        if label in {
            EvidenceLabel.UNSUPPORTED,
            EvidenceLabel.CONTRADICTED,
        }:
            issues.append(
                InspectorIssue(
                    category=InspectionCategory.HALLUCINATION,
                    severity=Severity.HIGH,
                    reason=(
                        f"Agent 结论缺乏证据支持（{label.value}）"
                    ),
                    recommendation=(
                        "重新检索知识库并补充证据，"
                        "无法确认时明确说明"
                    ),
                )
            )

        return issues

    @staticmethod
    def evaluate_evidence(
        agent_claim: str | None,
        evidence: list[EvidenceItem],
    ) -> dict[str, Any]:
        """返回证据评估结果（供 InspectionResult 记录）。"""
        return {
            "evidence_count": len(evidence),
            "label": label_evidence(
                agent_claim,
                evidence,
            ).value,
            "min_evidence": 1,
        }

    def _check_sufficiency(
        self,
        agent_claim: str | None,
        evidence: list[EvidenceItem],
    ) -> list[InspectorIssue]:
        if (
            agent_claim
            and agent_claim.strip()
            and len(evidence) < self.min_evidence
        ):
            return [
                InspectorIssue(
                    category=InspectionCategory.EVIDENCE,
                    severity=Severity.WARNING,
                    reason=(
                        f"Agent 给出结论，但证据仅 "
                        f"{len(evidence)} 条，低于最低要求 "
                        f"{self.min_evidence}"
                    ),
                    recommendation=(
                        "先收集足够证据，再给出结论"
                    ),
                )
            ]

        return []

    def _check_version(
        self,
        evidence: list[EvidenceItem],
        environment_version: str | None,
    ) -> list[InspectorIssue]:
        if not environment_version:
            return []

        mismatched = [
            item.source
            for item in evidence
            if item.version
            and item.version != "latest"
            and item.version != environment_version
        ]

        if mismatched:
            return [
                InspectorIssue(
                    category=InspectionCategory.VERSION,
                    severity=Severity.WARNING,
                    reason=(
                        f"知识版本与当前环境 "
                        f"{environment_version} 不匹配："
                        f"{mismatched}"
                    ),
                    recommendation=(
                        "使用与当前环境版本匹配的知识，"
                        "或重新检索"
                    ),
                )
            ]

        return []


__all__ = [
    "EvidenceJudge",
    "label_evidence",
]
