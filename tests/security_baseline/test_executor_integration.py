"""安全基线闸门接入 AgentExecutor / DagExecutor 的集成测试。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

import pytest

from agent.executor.executor import AgentExecutor
from agent.executor.dag_executor import DagExecutor
from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep
from agent.policies.policy_engine import PolicyEngine
from agent.safety.approval import ApprovalManager
from agent.security_baseline import (
    InMemoryAuditSink,
    SecurityBaselineEngine,
)
from agent.tools.registry import ToolRegistry


class FakeTool:
    def __init__(self, name: str, risk_level: str = "LOW", requires_approval: bool = False):
        self.name = name
        self.risk_level = risk_level
        self.requires_approval = requires_approval
        self.calls: list[dict] = []

    def execute(self, **arguments):
        self.calls.append(deepcopy(arguments))
        return {"success": True}


@pytest.fixture
def sink():
    return InMemoryAuditSink()


@pytest.fixture
def engine(sink):
    return SecurityBaselineEngine(audit_sink=sink)


def _executor(tool, engine):
    registry = ToolRegistry()
    registry.register(tool)
    return AgentExecutor(registry, PolicyEngine(), security_engine=engine)


def _context(**kw):
    base = {"request_id": "req-1", "user_id": "user-1"}
    base.update(kw)
    return ExecutionContext(**base)


# --------------------------------------------------------------------------
# L2 红线短路
# --------------------------------------------------------------------------


def test_redline_command_blocked_before_tool_invocation(engine, sink):
    tool = FakeTool("shell.execute", risk_level="HIGH", requires_approval=True)
    executor = _executor(tool, engine)
    step = PlanStep(1, "清理磁盘", "shell.execute", {"command": "rm -rf /var/log"})

    result = executor.execute(step, _context())

    assert result.success is False
    assert result.message == "操作被安全基线拦截"
    assert result.metadata["failure_class"] == "fatal"
    assert result.metadata["baseline_layer"] == "L2_OPERATIONS"
    assert tool.calls == []  # 红线短路，工具根本没被调用
    assert sink.event_types() == ["baseline.redline_hit"]
    # 原有 AuditRecord 链路同时留痕
    assert executor.get_audit_records()[-1].error.startswith("OL-001")


def test_compliance_redline_takes_priority(engine, sink):
    tool = FakeTool("shell.execute", risk_level="HIGH")
    executor = _executor(tool, engine)
    step = PlanStep(
        1, "探测", "shell.execute",
        {"command": "nmap -sV 10.0.0.1; rm -rf /"},
    )

    result = executor.execute(step, _context())

    assert result.success is False
    assert result.metadata["baseline_layer"] == "L0_COMPLIANCE"
    assert sink.event_types() == ["baseline.compliance_hit"]
    assert tool.calls == []


def test_benign_step_passes_through_baseline(engine, sink):
    tool = FakeTool("nginx.status", risk_level="LOW")
    executor = _executor(tool, engine)
    step = PlanStep(1, "查状态", "nginx.status", {"service": "nginx"})

    result = executor.execute(step, _context())

    assert result.success is True
    assert tool.calls == [{"service": "nginx"}]
    # 正常放行不产生基线审计事件
    assert sink.events() == []


# --------------------------------------------------------------------------
# L1 限流
# --------------------------------------------------------------------------


def test_quota_exhaustion_blocks_tool(tmp_path, sink):
    # 小容量配额配置：默认工具桶容量 3，避免循环上百次
    cfg = tmp_path / "small-quota.yaml"
    cfg.write_text(
        """
enforcement:
  fail_closed: true
L1_GENERIC_AI:
  quotas:
    tool_default:
      capacity: 3
      refill_per_second: 0
    tool_high_risk:
      capacity: 1
      refill_per_second: 0
""",
        encoding="utf-8",
    )
    engine = SecurityBaselineEngine(config_path=str(cfg), audit_sink=sink)
    tool = FakeTool("nginx.status", risk_level="LOW")
    executor = _executor(tool, engine)
    step = PlanStep(1, "查状态", "nginx.status", {"service": "nginx"})

    for _ in range(3):
        assert executor.execute(step, _context()).success is True
    blocked = executor.execute(step, _context())

    assert blocked.success is False
    assert blocked.message == "操作被安全基线拦截"
    assert "QUOTA_EXHAUSTED" in blocked.error
    assert sink.event_types()[-1] == "quota.exhausted"


def test_dry_run_still_blocks_redline_but_skips_quota(tmp_path, sink):
    cfg = tmp_path / "small-quota.yaml"
    cfg.write_text(
        """
enforcement:
  fail_closed: true
L1_GENERIC_AI:
  quotas:
    tool_default:
      capacity: 3
      refill_per_second: 0
    tool_high_risk:
      capacity: 1
      refill_per_second: 0
""",
        encoding="utf-8",
    )
    engine = SecurityBaselineEngine(config_path=str(cfg), audit_sink=sink)
    tool = FakeTool("nginx.status", risk_level="LOW")
    registry = ToolRegistry()
    registry.register(tool)
    executor = AgentExecutor(registry, PolicyEngine(), security_engine=engine)
    benign = PlanStep(1, "查状态", "nginx.status", {"service": "nginx"})

    # dry-run 不消耗配额：超过桶容量仍全部通过
    dry_context = _context(dry_run=True)
    for _ in range(10):
        assert executor.execute(benign, dry_context).success is True

    # 红线在 dry-run 下依旧拦截，计划校验阶段就拦住危险步骤
    evil = PlanStep(2, "删表", "nginx.status", {"command": "DROP TABLE orders"})
    blocked = executor.execute(evil, dry_context)
    assert blocked.success is False
    assert blocked.metadata["baseline_layer"] == "L2_OPERATIONS"


# --------------------------------------------------------------------------
# 审批审计事件
# --------------------------------------------------------------------------


def test_approval_requested_and_granted_are_audited(engine, sink):
    tool = FakeTool("server.restart", risk_level="HIGH", requires_approval=True)
    registry = ToolRegistry()
    registry.register(tool)
    manager = ApprovalManager(clock=lambda: datetime(2026, 11, 17, tzinfo=timezone.utc))
    policy = PolicyEngine(approval_manager=manager)
    executor = AgentExecutor(registry, policy, security_engine=engine)

    step = PlanStep(1, "重启", "server.restart", {"service": "mysql"}, requires_approval=True)
    context = _context()

    denied = executor.execute(step, context)
    assert denied.success is False
    assert sink.event_types() == ["approval.requested"]

    request = manager.create_for_step(context, step, ttl_seconds=300)
    manager.approve(request.approval_id, "reviewer-1")
    context.approval_id = request.approval_id

    granted = executor.execute(step, context)
    assert granted.success is True
    assert sink.event_types() == ["approval.requested", "approval.granted"]


# --------------------------------------------------------------------------
# DAG 执行器：基线 fatal 让下游自动 skip
# --------------------------------------------------------------------------


def test_dag_baseline_fatal_marks_downstream_skipped(engine, sink):
    dangerous = FakeTool("shell.execute", risk_level="HIGH")
    downstream = FakeTool("nginx.status", risk_level="LOW")
    registry = ToolRegistry()
    registry.register(dangerous)
    registry.register(downstream)
    executor = DagExecutor(registry, PolicyEngine(), security_engine=engine)

    first = PlanStep(1, "危险步骤", "shell.execute", {"command": "rm -rf /"})
    second = PlanStep(2, "下游步骤", "nginx.status", {}, depends_on=[1])

    plan = executor.execute_dag([second, first], _context())

    assert plan.status == "aborted_fatal"
    assert dangerous.calls == []
    assert downstream.calls == []
    skipped = [r for r in plan.step_results if r.metadata.get("failure_class") == "skipped"]
    assert len(skipped) == 1
    assert sink.event_types() == ["baseline.redline_hit"]


# --------------------------------------------------------------------------
# 向后兼容：不挂引擎时行为不变
# --------------------------------------------------------------------------


def test_executor_without_engine_keeps_legacy_behavior():
    tool = FakeTool("shell.execute", risk_level="HIGH", requires_approval=True)
    registry = ToolRegistry()
    registry.register(tool)
    executor = AgentExecutor(registry, PolicyEngine())

    # 没有基线引擎时，危险命令不会被基线拦，只走原 PolicyEngine 审批链
    result = executor.execute(
        PlanStep(1, "清理", "shell.execute", {"command": "rm -rf /"}),
        _context(),
    )
    assert result.success is False
    assert result.message == "操作被策略阻止"
    assert "baseline_layer" not in result.metadata
