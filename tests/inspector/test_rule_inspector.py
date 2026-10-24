"""
Rule Inspector（Level 1）测试。
"""

from agent.inspector.enums import InspectionCategory, Severity
from agent.inspector.judges.rule_judge import (
    RuleJudge,
    expected_risk,
    is_state_changing,
)
from agent.inspector.models import ToolCallRecord


def _categories(issues):
    return {i.category for i in issues}


def test_is_state_changing():
    assert is_state_changing("redis.restart")
    assert is_state_changing("nginx.stop")
    assert not is_state_changing("nginx.status")


def test_expected_risk_from_policy():
    policy = {"tool_risks": {"redis.restart": "HIGH"}}
    assert expected_risk("redis.restart", policy) == "HIGH"


def test_risk_misclassification():
    judge = RuleJudge()
    calls = [
        ToolCallRecord(
            tool_name="redis.restart",
            risk="LOW",
            approval_granted=True,
        )
    ]
    policy = {"tool_risks": {"redis.restart": "HIGH"}}

    issues = judge.check(
        {"tool_calls": calls, "policy": policy}
    )

    assert InspectionCategory.RISK in _categories(issues)

    issue = next(
        i for i in issues
        if i.category == InspectionCategory.RISK
    )
    assert issue.severity == Severity.HIGH


def test_approval_bypass():
    judge = RuleJudge()
    calls = [
        ToolCallRecord(
            tool_name="nginx.restart",
            risk="HIGH",
            approval_granted=False,
            success=True,
        )
    ]
    policy = {"tool_risks": {"nginx.restart": "HIGH"}}

    issues = judge.check(
        {"tool_calls": calls, "policy": policy}
    )

    assert (
        InspectionCategory.APPROVAL
        in _categories(issues)
    )

    issue = next(
        i for i in issues
        if i.category == InspectionCategory.APPROVAL
    )
    assert issue.severity == Severity.CRITICAL


def test_tool_loop_detected():
    judge = RuleJudge(loop_threshold=10)
    calls = [
        ToolCallRecord(tool_name="nginx.status", risk="LOW")
        for _ in range(11)
    ]

    issues = judge.check(
        {"tool_calls": calls, "policy": {}}
    )

    assert InspectionCategory.LOOP in _categories(issues)


def test_premature_state_changing_action():
    judge = RuleJudge()
    calls = [
        ToolCallRecord(
            tool_name="redis.restart",
            risk="LOW",
            approval_granted=False,
        )
    ]

    issues = judge.check(
        {
            "tool_calls": calls,
            "policy": {},
            "evidence": [],
        }
    )

    assert (
        InspectionCategory.PLANNING
        in _categories(issues)
    )
