"""
Evidence Inspector（Level 2）测试。
"""

from agent.inspector.enums import (
    EvidenceLabel,
    InspectionCategory,
)
from agent.inspector.judges.evidence_judge import (
    EvidenceJudge,
    label_evidence,
)
from agent.inspector.models import EvidenceItem


def _categories(issues):
    return {i.category for i in issues}


def test_label_supported():
    claim = "nginx 502 由 upstream 超时导致"
    evidence = [
        EvidenceItem(
            content="nginx 502 常见原因是 upstream 超时",
            source="nginx.md",
        )
    ]

    assert (
        label_evidence(claim, evidence)
        == EvidenceLabel.SUPPORTED
    )


def test_label_unsupported_without_evidence():
    assert (
        label_evidence("Redis 内存使用 92%", [])
        == EvidenceLabel.UNSUPPORTED
    )


def test_evidence_insufficient():
    judge = EvidenceJudge(min_evidence=1)
    issues = judge.check(
        {
            "agent_claim": "Redis 内存使用 92%",
            "evidence": [],
        }
    )

    assert (
        InspectionCategory.EVIDENCE
        in _categories(issues)
    )


def test_hallucination_when_unsupported():
    judge = EvidenceJudge(min_evidence=1)
    issues = judge.check(
        {
            "agent_claim": "Redis 内存使用 92%",
            "evidence": [],
        }
    )

    assert (
        InspectionCategory.HALLUCINATION
        in _categories(issues)
    )


def test_version_mismatch():
    judge = EvidenceJudge()
    issues = judge.check(
        {
            "agent_claim": None,
            "evidence": [
                EvidenceItem(
                    content="旧版配置方式",
                    source="nginx-guide.md",
                    version="1.18",
                )
            ],
            "environment_version": "1.20",
        }
    )

    assert (
        InspectionCategory.VERSION
        in _categories(issues)
    )
