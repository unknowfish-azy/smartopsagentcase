"""Breaks caught: mismatched correlation, leaked payloads and false success events."""
import logging

from agent.runtime_events import RunIdentity, terminal_event
from tests.agent.test_execution_approval import approved_setup


def test_event_is_minimal_and_uses_one_stable_run():
    identity = RunIdentity.create(request_id="req-1", task_id="task-1")
    first = terminal_event(identity, "executor", "failed", step_id=4)
    second = terminal_event(identity, "executor", "denied", step_id=4)
    assert first["request_id"] == second["request_id"] == "req-1"
    assert first["run_id"] == second["run_id"]
    assert first["event_id"] != second["event_id"]
    assert first["step_id"] == "4"
    assert set(first) == {"schema_version", "event_id", "request_id", "task_id", "run_id", "step_id", "source", "status", "timestamp"}


def test_hostile_ids_cannot_inject_log_lines_or_unbounded_payload():
    identity = RunIdentity.create(request_id="bad\nAuthorization: secret", task_id="x" * 10000)
    record = terminal_event(identity, "ai-service", "failed")
    assert "secret" not in str(record)
    assert "\n" not in record["request_id"]
    assert len(record["task_id"]) <= 96


def test_tool_failure_and_replay_emit_correlated_failure_and_denial(caplog):
    caplog.set_level(logging.INFO)
    _, _, runtime, tool, planned, context = approved_setup({"success": False, "password": "do-not-export"})
    context.task_id = "task-1"
    failed = runtime.execute(planned, context)
    denied = runtime.execute(planned, context)
    assert failed.metadata["run_event"]["status"] == "failed"
    assert denied.metadata["run_event"]["status"] == "denied"
    assert failed.metadata["run_event"]["task_id"] == "task-1"
    assert failed.metadata["run_event"]["run_id"] == denied.metadata["run_event"]["run_id"]
    assert "do-not-export" not in str(runtime.get_run_events())
    assert len(tool.calls) == 1
    assert "executor.terminal" in caplog.text
    assert "status=failed" in caplog.text
    assert "status=denied" in caplog.text
    assert failed.metadata["run_event"]["run_id"] in caplog.text
    assert "do-not-export" not in caplog.text


def test_dry_run_event_does_not_report_completed_action():
    _, _, runtime, tool, planned, context = approved_setup()
    context.dry_run = True
    result = runtime.execute(planned, context)
    assert result.metadata["run_event"]["status"] == "dry_run"
    assert tool.calls == []
