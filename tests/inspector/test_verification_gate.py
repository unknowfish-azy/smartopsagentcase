import pytest

from agent.inspector.enums import InspectionCategory, InspectionStatus, Severity
from agent.inspector.models import EvidenceItem, ToolCallRecord
from agent.inspector.pipeline import InspectorPipeline


def inspect(claim, actual_state=None, **extra):
    return InspectorPipeline().run({
        "agent_claim": claim,
        "actual_state": actual_state,
        "evidence": [EvidenceItem(content=claim or "", source="test")],
        **extra,
    })


@pytest.mark.parametrize("state", [None, {}, {"probes": []}, {"probes": ["bad"]}, {"probes": [{"probe_type": "unknown"}]}])
def test_success_claim_without_usable_observation_needs_review(state):
    result = inspect("任务已解决", state)
    assert result.status == InspectionStatus.WARN
    assert result.requires_human is True
    assert result.category == InspectionCategory.VERIFICATION
    assert result.severity == Severity.WARNING
    assert result.verification_result["status"] == "unverified"
    assert result.verification_result["required"] is True


def test_unknown_claim_with_failed_probe_does_not_pass():
    result = inspect("处理就这样了", {"probes": [{"probe_type": "http", "status_code": 502}]})
    assert result.status == InspectionStatus.WARN
    assert result.requires_human is True
    assert result.verification_result["status"] == "uncertain"


def test_positive_observation_can_pass():
    result = inspect("任务已解决", {"probes": [{"probe_type": "http", "status_code": 200}]})
    assert result.status == InspectionStatus.PASS
    assert result.requires_human is False
    assert result.verification_result["status"] == "verified"


def test_diagnostic_claim_does_not_require_execution_observation():
    result = inspect("nginx 502 由 upstream 超时导致")
    assert result.status == InspectionStatus.PASS
    assert result.verification_result["status"] == "not_required"


@pytest.mark.parametrize("claim", ["诊断：解决方案是调整 nginx upstream", "如何解决 nginx 502：检查 upstream"])
def test_solution_language_is_not_execution_success(claim):
    result = inspect(claim)
    assert result.status == InspectionStatus.PASS
    assert result.verification_result["status"] == "not_required"


def test_explicit_verification_request_requires_observation():
    result = inspect("处理就这样了", metadata={"verification_required": True})
    assert result.status == InspectionStatus.WARN
    assert result.requires_human is True


@pytest.mark.parametrize("risk", ["high", "HIGH", "critical", "CRITICAL"])
def test_successful_risky_tool_requires_observations_regardless_of_case(risk):
    result = inspect("处理就这样了", tool_calls=[ToolCallRecord(tool_name="server.restart", risk=risk, approval_granted=True, success=True)])
    assert result.verification_result["required"] is True
    assert result.requires_human is True


def test_suggested_solution_does_not_hide_separate_success_claim():
    result = inspect("解决方案已记录。服务已恢复", {"probes": [{"probe_type": "http", "status_code": 502}]})
    assert result.status == InspectionStatus.REJECTED


def test_unverified_execution_does_not_downgrade_policy_violation():
    result = inspect("任务已解决", tool_calls=[ToolCallRecord(tool_name="nginx.restart", risk="HIGH", approval_granted=False, success=True)], policy={"tool_risks": {"nginx.restart": "HIGH"}})
    assert result.status == InspectionStatus.VIOLATION
    assert result.requires_human is True
    assert result.verification_result["status"] == "unverified"


def test_false_success_remains_rejected():
    result = inspect("任务已解决", {"probes": [{"probe_type": "http", "status_code": 502}]})
    assert result.status == InspectionStatus.REJECTED
    assert result.verification_result["status"] == "failed"
