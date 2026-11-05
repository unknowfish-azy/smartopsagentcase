"""
EventBus + Inspector 集成测试（Phase 6）。

验证 TraceCollector 监听 Agent EventBus，
并将执行轨迹交给 InspectorService 纠察。
"""

import asyncio

from agent.inspector.collectors.trace_collector import TraceCollector
from agent.inspector.enums import (
    InspectionCategory,
    InspectionStatus,
)
from agent.inspector.service import InspectorService
from agent.kernel.event.bus import EventBus
from agent.kernel.event.events import (
    APPROVAL_GRANTED,
    EXECUTION_FINISHED,
    EXECUTION_STARTED,
    TOOL_AFTER_CALL,
    TOOL_BEFORE_CALL,
    VERIFICATION_FINISHED,
    AgentEvent,
)


def _run(coro):
    return asyncio.run(coro)


def test_trace_collector_approval_bypass():
    async def scenario():
        bus = EventBus()
        collector = TraceCollector().subscribe(bus)
        service = InspectorService()

        await bus.publish(
            AgentEvent(
                name=EXECUTION_STARTED,
                request_id="TASK-100",
            )
        )
        await bus.publish(
            AgentEvent(
                name=TOOL_BEFORE_CALL,
                request_id="TASK-100",
                payload={
                    "tool_name": "nginx.restart",
                    "risk": "HIGH",
                },
            )
        )
        await bus.publish(
            AgentEvent(
                name=TOOL_AFTER_CALL,
                request_id="TASK-100",
                payload={
                    "tool_name": "nginx.restart",
                    "risk": "HIGH",
                    "approval_granted": False,
                    "success": True,
                },
            )
        )

        context = collector.build_context(
            "TASK-100",
            policy={"tool_risks": {"nginx.restart": "HIGH"}},
        )

        return service.pipeline.run(context)

    result = _run(scenario())

    assert result.status == InspectionStatus.VIOLATION
    assert any(
        issue.category == InspectionCategory.APPROVAL
        for issue in result.issues
    )


def test_trace_collector_false_success():
    async def scenario():
        bus = EventBus()
        collector = TraceCollector().subscribe(bus)
        service = InspectorService()

        await bus.publish(
            AgentEvent(
                name=TOOL_AFTER_CALL,
                request_id="TASK-200",
                payload={
                    "tool_name": "nginx.restart",
                    "risk": "HIGH",
                    "approval_granted": True,
                    "success": True,
                },
            )
        )
        await bus.publish(
            AgentEvent(
                name=VERIFICATION_FINISHED,
                request_id="TASK-200",
                payload={"probes": [{"type": "http", "status_code": 502}]},
            )
        )

        context = collector.build_context(
            "TASK-200",
            agent_claim="问题已解决",
            policy={"tool_risks": {"nginx.restart": "HIGH"}},
        )

        return service.pipeline.run(context)

    result = _run(scenario())

    assert result.status == InspectionStatus.REJECTED
    assert result.category == InspectionCategory.VERIFICATION


def test_trace_collector_tool_calls():
    async def scenario():
        bus = EventBus()
        collector = TraceCollector().subscribe(bus)

        await bus.publish(
            AgentEvent(
                name=TOOL_AFTER_CALL,
                request_id="TASK-300",
                payload={
                    "tool_name": "nginx.status",
                    "risk": "LOW",
                    "success": True,
                },
            )
        )
        await bus.publish(
            AgentEvent(
                name=APPROVAL_GRANTED,
                request_id="TASK-300",
                payload={"operation": "nginx.status"},
            )
        )
        await bus.publish(
            AgentEvent(
                name=EXECUTION_FINISHED,
                request_id="TASK-300",
            )
        )

        return collector.tool_calls("TASK-300")

    calls = _run(scenario())

    assert len(calls) == 1
    assert calls[0].tool_name == "nginx.status"
    assert calls[0].approval_granted is True
