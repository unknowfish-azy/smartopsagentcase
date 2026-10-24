from unittest.mock import Mock

from agent.inspector.models import EvidenceItem
from agent.inspector.persistence import BackendInspectorClient
from agent.inspector.service import InspectorService


def test_inspect_and_persist_records_pipeline_result():
    client = Mock()
    evidence = [EvidenceItem(content="upstream timed out", source="nginx.log")]

    result = InspectorService().inspect_and_persist(
        client,
        task_id="TASK-PERSIST-001",
        agent_claim="upstream timed out",
        evidence=evidence,
    )

    client.record.assert_called_once_with(result, evidence)
    assert result.task_id == "TASK-PERSIST-001"


def test_backend_client_requires_internal_token():
    try:
        BackendInspectorClient("http://localhost:8080", "")
    except ValueError as exc:
        assert "internal_token" in str(exc)
    else:
        raise AssertionError("empty internal token was accepted")
