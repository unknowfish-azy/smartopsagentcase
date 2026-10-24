"""
Inspector Pipeline 端到端测试。
"""

from agent.inspector.enums import (
    InspectionCategory,
    InspectionStatus,
)
from agent.inspector.models import (
    EvidenceItem,
    ToolCallRecord,
)
from agent.inspector.service import InspectorService


def _service():
    return InspectorService()


def test_clean_pass():
    result = _service().inspect(
        task_id="TASK-001",
        agent_claim="nginx 502 由 upstream 超时导致",
        evidence=[
            EvidenceItem(
                content="nginx 502 常见原因是 upstream 超时",
                source="nginx.md",
                version="latest",
            )
        ],
        tool_calls=[
            ToolCallRecord(
                tool_name="nginx.status",
                risk="LOW",
                approval_granted=False,
                success=True,
            )
        ],
    )

    assert result.status == InspectionStatus.PASS
    assert not result.requires_human


def test_false_success_rejected():
    result = _service().inspect(
        task_id="TASK-002",
        agent_claim="问题已解决",
        evidence=[
            EvidenceItem(
                content="nginx 已重启成功",
                source="execution.log",
            )
        ],
        tool_calls=[
            ToolCallRecord(
                tool_name="nginx.restart",
                risk="HIGH",
                approval_granted=True,
                success=True,
            )
        ],
        policy={"tool_risks": {"nginx.restart": "HIGH"}},
        actual_state={"resolved": False, "status": "502"},
    )

    assert result.status == InspectionStatus.REJECTED
    assert result.category == InspectionCategory.VERIFICATION
    assert result.requires_human


def test_premature_restart_violation():
    result = _service().inspect(
        task_id="TASK-003",
        agent_claim=None,
        evidence=[],
        tool_calls=[
            ToolCallRecord(
                tool_name="redis.restart",
                risk="LOW",
                approval_granted=False,
                success=True,
            )
        ],
    )

    assert result.status == InspectionStatus.VIOLATION
    assert result.requires_human
    assert any(
        issue.category == InspectionCategory.PLANNING
        for issue in result.issues
    )


def test_approval_bypass_critical():
    result = _service().inspect(
        task_id="TASK-004",
        agent_claim=None,
        evidence=[
            EvidenceItem(content="redis 内存占用高")
        ],
        tool_calls=[
            ToolCallRecord(
                tool_name="redis.restart",
                risk="LOW",
                approval_granted=False,
                success=True,
            )
        ],
        policy={"tool_risks": {"redis.restart": "HIGH"}},
    )

    assert result.status == InspectionStatus.VIOLATION
    assert any(
        issue.category == InspectionCategory.APPROVAL
        for issue in result.issues
    )
