"""No actual system actions: recording tools exercise policy/executor behavior."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from agent.executor.executor import AgentExecutor
from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep
from agent.policies.policy_engine import PolicyEngine
from agent.safety.approval import ApprovalManager
from agent.tools.registry import ToolRegistry


class RecordingTool:
    name = "server.restart"
    risk_level = "HIGH"
    requires_approval = True

    def __init__(self, output=None):
        self.calls = []
        self.output = {"success": True} if output is None else output

    def execute(self, **arguments):
        self.calls.append(deepcopy(arguments))
        return self.output


def step():
    return PlanStep(1, "重启 mysql", "server.restart", {"service": "mysql"}, requires_approval=True)


def executor(tool, policy):
    registry = ToolRegistry()
    registry.register(tool)
    return AgentExecutor(registry, policy)


def approved_setup(output=None):
    now = [datetime(2026, 11, 4, tzinfo=timezone.utc)]
    manager = ApprovalManager(clock=lambda: now[0])
    policy = PolicyEngine(approval_manager=manager)
    context = ExecutionContext("request-1", "user-1", environment="lab")
    planned = step()
    request = manager.create_for_step(context, planned, ttl_seconds=30)
    manager.approve(request.approval_id, "reviewer-1")
    context.approval_id = request.approval_id
    tool = RecordingTool(output)
    return now, manager, executor(tool, policy), tool, planned, context


def test_requires_approval_flag_never_counts_as_approval():
    tool = RecordingTool()
    result = executor(tool, PolicyEngine()).execute(step(), ExecutionContext("r", "u"))
    assert result.success is False
    assert tool.calls == []


def test_explicit_tool_failure_is_not_wrapped_as_success():
    tool = RecordingTool({"success": False, "error": "probe failed"})
    tool.name = "knowledge.search"
    tool.risk_level = "LOW"
    tool.requires_approval = False
    runtime = executor(tool, PolicyEngine())
    result = runtime.execute(PlanStep(1, "query", tool.name, {}), ExecutionContext("r", "u"))
    assert result.success is False
    assert result.error == "probe failed"
    assert runtime.get_audit_records()[-1].success is False


def test_grant_runs_only_the_approved_target_once():
    _, _, runtime, tool, planned, context = approved_setup()
    assert runtime.execute(planned, context).success is True
    assert runtime.execute(planned, context).success is False
    assert tool.calls == [{"service": "mysql"}]


@pytest.mark.parametrize("change", ["request", "user", "environment", "run", "step", "tool", "action", "argument", "nested_argument"])
def test_approval_cannot_authorize_a_different_execution(change):
    _, _, runtime, tool, planned, context = approved_setup()
    if change == "request": context.request_id = "other"
    elif change == "run": context.run_id = "other-run"
    elif change == "user": context.user_id = "other"
    elif change == "environment": context.environment = "production"
    elif change == "step": planned.step_id = 2
    elif change == "tool": planned.tool_name = "unknown"
    elif change == "action": planned.action = "different"
    elif change == "argument": planned.arguments["service"] = "redis"
    else: planned.arguments["extra"] = {"host": "other"}
    assert runtime.execute(planned, context).success is False
    assert tool.calls == []


def test_approval_is_bound_to_run_id():
    """SEC-04：同一 request/step/参数在不同 run 下不得复用审批。"""
    now = [datetime(2026, 11, 4, tzinfo=timezone.utc)]
    manager = ApprovalManager(clock=lambda: now[0])
    planned = step()
    first = ExecutionContext("request-1", "user-1", environment="lab")
    request = manager.create_for_step(first, planned, ttl_seconds=30)
    manager.approve(request.approval_id, "reviewer-1")
    second = ExecutionContext("request-1", "user-1", environment="lab")
    assert second.run_id != first.run_id
    assert manager.validate(request.approval_id, second, planned) is False


def test_approval_from_another_run_denies_execution():
    _, _, runtime, tool, planned, context = approved_setup()
    other_run = ExecutionContext("request-1", "user-1", environment="lab")
    other_run.approval_id = context.approval_id
    assert runtime.execute(planned, other_run).success is False
    assert tool.calls == []


def test_approval_requires_run_identity():
    context = ExecutionContext("r", "u")
    context.run_id = ""
    with pytest.raises(ValueError):
        ApprovalManager().create_for_step(context, step())


def test_legacy_create_request_is_deprecated():
    manager = ApprovalManager()
    with pytest.warns(DeprecationWarning):
        manager.create_request("r", "server.restart", "legacy", "u")


def test_requester_cannot_approve_own_request():
    manager = ApprovalManager()
    context = ExecutionContext("r", "u")
    request = manager.create_for_step(context, step())
    with pytest.raises(ValueError):
        manager.approve(request.approval_id, "u")


def test_expiration_denies_execution():
    now, _, runtime, tool, planned, context = approved_setup()
    now[0] += timedelta(seconds=31)
    assert runtime.execute(planned, context).success is False
    assert tool.calls == []


def test_rejection_revokes_an_unconsumed_approval():
    _, manager, runtime, tool, planned, context = approved_setup()
    manager.reject(context.approval_id, "reviewer-1")
    assert runtime.execute(planned, context).success is False
    assert tool.calls == []


def test_returned_approval_snapshot_cannot_forge_internal_state():
    manager = ApprovalManager()
    context = ExecutionContext("r", "u")
    planned = step()
    request = manager.create_for_step(context, planned)
    context.approval_id = request.approval_id
    # Mere possession of an ID or fake metadata approval is not a grant.
    context.metadata["approval_granted"] = True
    tool = RecordingTool()
    assert executor(tool, PolicyEngine(approval_manager=manager)).execute(planned, context).success is False
    assert tool.calls == []


def test_dry_run_does_not_consume_grant_or_call_tool():
    _, _, runtime, tool, planned, context = approved_setup()
    context.dry_run = True
    assert runtime.execute(planned, context).success is True
    assert tool.calls == []
    context.dry_run = False
    assert runtime.execute(planned, context).success is True


def test_concurrent_replay_executes_exactly_once():
    _, _, runtime, tool, planned, context = approved_setup()
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: runtime.execute(planned, context), range(8)))
    assert sum(result.success for result in results) == 1
    assert tool.calls == [{"service": "mysql"}]


def test_tool_failure_still_consumes_the_grant():
    _, _, runtime, tool, planned, context = approved_setup({"success": False, "error": "failed"})
    assert runtime.execute(planned, context).success is False
    assert runtime.execute(planned, context).success is False
    assert len(tool.calls) == 1
    assert runtime.get_audit_records()[0].success is False


@pytest.mark.parametrize("output", [{"success": "false"}, {"success": None}])
def test_malformed_tool_success_is_not_truthy_success(output):
    _, _, runtime, _, planned, context = approved_setup(output)
    assert runtime.execute(planned, context).success is False


def test_unknown_approval_id_is_denied():
    manager = ApprovalManager()
    with pytest.raises(ValueError):
        manager.approve("invented", "reviewer")


def test_critical_tool_remains_denied_even_with_grant():
    _, _, runtime, tool, planned, context = approved_setup()
    tool.risk_level = "CRITICAL"
    assert runtime.execute(planned, context).success is False
    assert tool.calls == []


def test_low_classifier_cannot_override_tool_declared_risk():
    tool = RecordingTool()
    tool.name = "custom.change"
    planned = PlanStep(1, "change", tool.name, {}, requires_approval=False)
    assert executor(tool, PolicyEngine()).execute(planned, ExecutionContext("r", "u")).success is False
    assert tool.calls == []


def test_read_only_payload_without_success_field_remains_compatible():
    tool = RecordingTool({"documents": []})
    tool.name, tool.risk_level, tool.requires_approval = "knowledge.search", "LOW", False
    result = executor(tool, PolicyEngine()).execute(PlanStep(1, "query", tool.name, {}), ExecutionContext("r", "u"))
    assert result.success is True
    assert result.output == {"documents": []}


def test_declared_risk_enum_is_accepted():
    from agent.policies.risk import RiskLevel
    _, _, runtime, tool, planned, context = approved_setup()
    tool.risk_level = RiskLevel.HIGH
    assert runtime.execute(planned, context).success is True


def test_structured_tool_result_failure_is_propagated():
    from agent.tools.adapters.python import PythonToolResult
    _, _, runtime, _, planned, context = approved_setup(PythonToolResult("server.restart", None, 1, success=False, error="adapter failed"))
    result = runtime.execute(planned, context)
    assert result.success is False
    assert result.error == "adapter failed"


def test_bound_step_snapshot_is_not_changed_by_later_caller_mutation():
    now, manager, runtime, tool, planned, context = approved_setup()
    original_authorize = runtime.policy_engine.authorize_execution

    def authorize(registered, frozen_context, frozen_step):
        decision = original_authorize(registered, frozen_context, frozen_step)
        planned.arguments["service"] = "redis"
        context.user_id = "other"
        return decision

    runtime.policy_engine.authorize_execution = authorize
    assert runtime.execute(planned, context).success is True
    assert tool.calls == [{"service": "mysql"}]


def test_legacy_approval_is_informational_and_cannot_authorize_tool():
    manager = ApprovalManager()
    request = manager.create_request("r", "server.restart", "legacy", "u")
    manager.approve("r", "reviewer")
    context = ExecutionContext("r", "u", approval_id=request.approval_id)
    tool = RecordingTool()
    assert executor(tool, PolicyEngine(approval_manager=manager)).execute(step(), context).success is False
    assert tool.calls == []


def test_expired_approval_cannot_be_approved_later():
    now = [datetime(2026, 11, 4, tzinfo=timezone.utc)]
    manager = ApprovalManager(clock=lambda: now[0])
    request = manager.create_for_step(ExecutionContext("r", "u"), step(), ttl_seconds=1)
    now[0] += timedelta(seconds=1)
    with pytest.raises(ValueError):
        manager.approve(request.approval_id, "reviewer")


def test_used_grant_cannot_be_reapproved():
    _, manager, runtime, _, planned, context = approved_setup()
    assert runtime.execute(planned, context).success is True
    with pytest.raises(ValueError):
        manager.approve(context.approval_id, "reviewer")


def test_read_only_policy_check_does_not_consume_grant():
    _, _, runtime, tool, planned, context = approved_setup()
    assert runtime.policy_engine.check(tool, context, planned).allowed is True
    assert runtime.policy_engine.check(tool, context, planned).allowed is True
    assert runtime.execute(planned, context).success is True


@pytest.mark.parametrize("arguments", [{1: "mysql"}, {"target": ("mysql",)}, {"threshold": float("nan")}])
def test_approval_rejects_non_json_arguments_without_ambiguous_fingerprint(arguments):
    planned = step()
    planned.arguments = arguments
    with pytest.raises(ValueError):
        ApprovalManager().create_for_step(ExecutionContext("r", "u"), planned)


def test_malformed_approval_id_does_not_raise_or_allow_execution():
    _, _, runtime, tool, planned, context = approved_setup()
    context.approval_id = {"fake": True}
    assert runtime.execute(planned, context).success is False
    assert tool.calls == []


def test_tool_exception_consumes_grant_and_is_audited():
    _, _, runtime, tool, planned, context = approved_setup()

    def fail(**kwargs):
        raise RuntimeError("failed before completing action")

    tool.execute = fail
    result = runtime.execute(planned, context)
    assert result.success is False
    assert "failed before completing action" in result.error
    assert runtime.get_audit_records()[0].success is False
    assert runtime.execute(planned, context).success is False


def test_cyclic_arguments_fail_closed_with_audit():
    _, _, runtime, tool, planned, context = approved_setup()
    planned.arguments["cycle"] = planned.arguments
    result = runtime.execute(planned, context)
    assert result.success is False
    assert tool.calls == []
    assert runtime.get_audit_records()[0].success is False
