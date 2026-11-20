"""W4 验收：Product Tool Bus 写 5 工具。

覆盖：
1. 写工具分类：3 个 REVIEW 型（MEDIUM）、1 个审批型（HIGH）、1 个急停兜底（CRITICAL 免审批）；
2. 审批闸门：无 approval_id 的 HIGH 写操作直接拒绝，且不发 HTTP；
3. REVIEW 强制：纠察事件状态永远 REVIEW、requiresHuman=true；
4. 审计必发：requested + succeeded 双事件；无发射器则 fail-closed；
5. 失败审计：403 时 requested + failed，异常仍按 PERMISSION 抛出；
6. PolicyEngine：HIGH 需审批、CRITICAL 默认拒绝、急停 safety_bypass 放行；
7. 写审计事件已加入基线白名单。
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import httpx
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.executor.models import ExecutionContext  # noqa: E402
from agent.planner.steps import PlanStep  # noqa: E402
from agent.policies.policy_engine import PolicyEngine  # noqa: E402
from agent.policies.risk import RiskLevel  # noqa: E402
from agent.security_baseline.loader import load_baseline  # noqa: E402
from agent.tools.builtin.product_actions import (  # noqa: E402
    WRITE_TOOL_METAS,
    build_product_action_tools,
)
from agent.tools.builtin.product_bus import ProductApiClient  # noqa: E402
from agent.tools.errors import ToolErrorCategory, ToolExecutionError  # noqa: E402

EXPECTED_CONTRACT = {
    "inspector.event.create": ("POST", "/api/inspector/check"),
    "knowledge.candidate.submit": ("POST", "/api/knowledge/candidates/from-log-diagnosis"),
    "runbook.draft.create": ("POST", "/api/runbooks"),
    "robot.task.create": ("POST", "/api/robot/devices/{deviceKey}/command"),
    "robot.estop": ("POST", "/api/robot/devices/{deviceKey}/estop"),
}


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event_type: str, **kwargs) -> None:
        self.events.append((event_type, kwargs))

    @property
    def names(self) -> list[str]:
        return [name for name, _ in self.events]


def _ctx(*, approval_id: str | None = None, dry_run: bool = False, emitter=None) -> ExecutionContext:
    metadata = {}
    if emitter is not None:
        metadata["audit_emitter"] = emitter
    return ExecutionContext(
        request_id="req_w4",
        user_id="u1",
        approval_id=approval_id,
        dry_run=dry_run,
        metadata=metadata,
    )


def _client(handler) -> ProductApiClient:
    return ProductApiClient(
        backend_base_url="http://backend.test",
        transport=httpx.MockTransport(handler),
    )


def _tools(handler, *, emitter=None):
    return {
        tool.name: tool
        for tool in build_product_action_tools(
            client=_client(handler), audit_emitter=emitter
        )
    }


def test_registry_exposes_five_gated_write_tools():
    tools = _tools(lambda request: httpx.Response(200, json={"data": {}}), emitter=Recorder())

    assert set(tools) == set(EXPECTED_CONTRACT)
    assert tools["inspector.event.create"].risk_level is RiskLevel.MEDIUM
    assert tools["knowledge.candidate.submit"].risk_level is RiskLevel.MEDIUM
    assert tools["runbook.draft.create"].risk_level is RiskLevel.MEDIUM
    assert tools["robot.task.create"].risk_level is RiskLevel.HIGH
    assert tools["robot.task.create"].requires_approval is True
    assert tools["robot.estop"].risk_level is RiskLevel.CRITICAL
    assert tools["robot.estop"].requires_approval is False
    assert tools["robot.estop"].safety_bypass is True
    for tool in tools.values():
        assert tool.definition.implementation_status.value == "REAL"


@pytest.mark.parametrize("meta", WRITE_TOOL_METAS, ids=lambda meta: meta.name)
def test_declared_write_paths_match_backend_contract(meta):
    assert (meta.method, meta.path) == EXPECTED_CONTRACT[meta.name]


def test_inspector_event_forces_review_state():
    seen: list[httpx.Request] = []
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"id": 9, "status": "REVIEW"}})

    tool = _tools(handler, emitter=recorder)["inspector.event.create"]
    result = asyncio.run(
        tool.execute(
            {
                "taskId": "task-1",
                "severity": "HIGH",
                "reason": "检测到异常",
                # 调用方试图直接改成已解决，必须被 force_fields 覆盖。
                "status": "RESOLVED",
                "requiresHuman": False,
            },
            _ctx(),
        )
    )

    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/inspector/check"
    assert body["status"] == "REVIEW"
    assert body["requiresHuman"] is True
    assert body["target"] == "AGENT"
    assert result["audit_emitted"] is True
    assert recorder.names == ["agent.write.requested", "agent.write.succeeded"]


def test_knowledge_candidate_submit_enters_pending_review():
    seen: list[httpx.Request] = []
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"status": "PENDING_REVIEW"}})

    tool = _tools(handler, emitter=recorder)["knowledge.candidate.submit"]
    asyncio.run(tool.execute({"title": "502 排查", "contentMarkdown": "正文"}, _ctx()))

    assert seen[0].url.path == "/api/knowledge/candidates/from-log-diagnosis"
    assert json.loads(seen[0].content) == {
        "title": "502 排查",
        "contentMarkdown": "正文",
    }
    assert recorder.names == ["agent.write.requested", "agent.write.succeeded"]


def test_runbook_draft_create_is_not_executable():
    seen: list[httpx.Request] = []
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"id": 3, "status": "DRAFT"}})

    tool = _tools(handler, emitter=recorder)["runbook.draft.create"]
    asyncio.run(tool.execute({"name": "重启预案"}, _ctx()))

    assert seen[0].url.path == "/api/runbooks"
    assert tool.definition.idempotency == "AT_MOST_ONCE"
    assert recorder.names == ["agent.write.requested", "agent.write.succeeded"]


def test_high_risk_robot_task_requires_approval_before_http():
    seen: list[httpx.Request] = []
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"dispatched": True}})

    tool = _tools(handler, emitter=recorder)["robot.task.create"]

    with pytest.raises(ToolExecutionError) as excinfo:
        asyncio.run(
            tool.execute({"deviceKey": "dev-1", "op": "MOVE"}, _ctx())
        )

    assert excinfo.value.category is ToolErrorCategory.PERMISSION
    assert seen == []
    assert recorder.events == []

    result = asyncio.run(
        tool.execute(
            {"deviceKey": "dev-1", "op": "MOVE"},
            _ctx(approval_id="approval-123"),
        )
    )
    body = json.loads(seen[0].content)
    assert seen[0].url.path == "/api/robot/devices/dev-1/command"
    assert body["source"] == "BRAIN"
    assert result["status"] == 200
    assert recorder.names == ["agent.write.requested", "agent.write.succeeded"]


def test_emergency_stop_bypasses_approval_but_is_audited():
    seen: list[httpx.Request] = []
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {"stopped": True}})

    tool = _tools(handler, emitter=recorder)["robot.estop"]
    result = asyncio.run(tool.execute({"deviceKey": "dev-9"}, _ctx()))

    assert seen[0].url.path == "/api/robot/devices/dev-9/estop"
    assert seen[0].content == b""
    assert result["ok"] is True
    assert recorder.names == ["agent.write.requested", "agent.write.succeeded"]


def test_write_without_audit_emitter_fails_closed():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {}})

    tool = _tools(handler)["runbook.draft.create"]

    with pytest.raises(ToolExecutionError) as excinfo:
        asyncio.run(tool.execute({"name": "无审计"}, _ctx()))

    assert excinfo.value.category is ToolErrorCategory.PERMISSION
    assert seen == []


def test_forbidden_write_emits_failed_audit_and_raises_permission():
    recorder = Recorder()
    tool = _tools(lambda request: httpx.Response(403, text="Forbidden"), emitter=recorder)[
        "robot.task.create"
    ]

    with pytest.raises(ToolExecutionError) as excinfo:
        asyncio.run(
            tool.execute(
                {"deviceKey": "dev-1", "op": "MOVE"},
                _ctx(approval_id="approval-123"),
            )
        )

    assert excinfo.value.category is ToolErrorCategory.PERMISSION
    assert recorder.names == ["agent.write.requested", "agent.write.failed"]


def test_dry_run_previews_without_http_or_audit():
    seen: list[httpx.Request] = []
    recorder = Recorder()

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"data": {}})

    tool = _tools(handler, emitter=recorder)["robot.task.create"]
    result = asyncio.run(
        tool.execute(
            {"deviceKey": "dev-1", "op": "MOVE"},
            _ctx(dry_run=True),
        )
    )

    assert seen == []
    assert result["dry_run"] is True
    assert result["body_keys"] == ["op", "source"]
    assert recorder.events == []


# --------------------------------------------------------------------------
# PolicyEngine 闸门
# --------------------------------------------------------------------------


def _step(name: str) -> PlanStep:
    return PlanStep(step_id=1, action="", tool_name=name, arguments={})


class _StubApproval:
    def validate(self, approval_id, context, step, consume: bool = False) -> bool:
        return bool(approval_id)


def test_policy_engine_gates_high_risk_write_on_approval():
    tools = _tools(lambda request: httpx.Response(200, json={"data": {}}), emitter=Recorder())
    engine = PolicyEngine()
    step = _step("robot.task.create")

    denied = engine.check(tools["robot.task.create"], _ctx(), step)
    assert denied.allowed is False
    assert denied.requires_approval is True

    engine_with_approval = PolicyEngine(approval_manager=_StubApproval())
    allowed = engine_with_approval.check(
        tools["robot.task.create"], _ctx(approval_id="approval-1"), step
    )
    assert allowed.allowed is True


def test_policy_engine_denies_critical_except_safety_bypass():
    tools = _tools(lambda request: httpx.Response(200, json={"data": {}}), emitter=Recorder())
    engine = PolicyEngine()

    estop = engine.check(tools["robot.estop"], _ctx(), _step("robot.estop"))
    assert estop.allowed is True

    class _CriticalTool:
        name = "danger.custom"
        risk_level = RiskLevel.CRITICAL
        requires_approval = True
        safety_bypass = False

    denied = engine.check(_CriticalTool(), _ctx(), _step("danger.custom"))
    assert denied.allowed is False
    assert "CRITICAL" in denied.reason


def test_write_audit_events_are_whitelisted_in_baseline():
    config = load_baseline()
    assert {
        "agent.write.requested",
        "agent.write.succeeded",
        "agent.write.failed",
    } <= config.audit_required_events
