"""Agent 执行链组合根（agent.assembly）装配测试。

覆盖：
* 默认装配的部件接线（引擎/注册中心/策略引擎/RobotPlugin 守卫）与 frozen 语义；
* dag 开关选择执行器类型、tools 预注册与重名拒绝；
* 红线端到端拦截 + 审计落盘（哈希链可验）；
* DAG fatal 下游 skipped；
* security_enabled=False 的纯旧行为回退；
* 审计历史被篡改后重新装配 fail-closed（ValueError）。

所有用例显式传 audit_dir=tmp_path，绝不污染仓库 data/ 目录。
"""

from __future__ import annotations

import json
from copy import deepcopy

import pytest

from agent.assembly import AgentAssembly, build_agent_assembly
from agent.executor.dag_executor import DagExecutor
from agent.executor.executor import AgentExecutor
from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep
from agent.plugins.installed.robot.tools import RobotVoiceCommandTool
from agent.security_baseline import (
    SecurityBaselineBundle,
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


def _context(**kw):
    base = {"request_id": "req-1", "user_id": "user-1"}
    base.update(kw)
    return ExecutionContext(**base)


def _voice_tool(plugin) -> RobotVoiceCommandTool:
    candidates = [t for t in plugin.tools if isinstance(t, RobotVoiceCommandTool)]
    assert len(candidates) == 1
    return candidates[0]


# --------------------------------------------------------------------------
# 默认装配：部件接线与不可变语义
# --------------------------------------------------------------------------


def test_default_assembly_is_fully_wired(tmp_path):
    assembly = build_agent_assembly(audit_dir=tmp_path / "audit")

    assert isinstance(assembly, AgentAssembly)
    assert isinstance(assembly.executor, AgentExecutor)
    assert not isinstance(assembly.executor, DagExecutor)
    assert isinstance(assembly.tool_registry, ToolRegistry)
    # 执行器与组合包共享同一个注册中心实例，接线在工厂内闭合
    assert assembly.executor.tool_registry is assembly.tool_registry
    assert assembly.executor.policy_engine is assembly.policy_engine

    # 安全基线默认开启（生产 fail-closed 语义）
    assert isinstance(assembly.baseline, SecurityBaselineBundle)
    assert isinstance(assembly.executor.security_engine, SecurityBaselineEngine)
    assert assembly.executor.security_engine is assembly.baseline.engine

    # RobotPlugin 语音工具守卫与 bundle.robot_guard 是同一个实例
    voice = _voice_tool(assembly.robot_plugin)
    assert voice.guard is assembly.baseline.robot_guard
    assert (tmp_path / "audit").is_dir()


def test_assembly_is_frozen(tmp_path):
    assembly = build_agent_assembly(audit_dir=tmp_path / "audit")
    with pytest.raises(AttributeError):
        assembly.executor = None  # type: ignore[misc]


def test_dag_flag_selects_dag_executor(tmp_path):
    assembly = build_agent_assembly(audit_dir=tmp_path / "audit", dag=True)
    assert isinstance(assembly.executor, DagExecutor)
    # DagExecutor 是 AgentExecutor 子类，基线引擎同样挂接
    assert assembly.executor.security_engine is assembly.baseline.engine


# --------------------------------------------------------------------------
# tools 预注册
# --------------------------------------------------------------------------


def test_tools_are_pre_registered_and_executable(tmp_path):
    tool = FakeTool("nginx.status", risk_level="LOW")
    assembly = build_agent_assembly(
        audit_dir=tmp_path / "audit", tools=[tool]
    )

    assert assembly.tool_registry.get("nginx.status") is tool

    result = assembly.executor.execute(
        PlanStep(1, "查状态", "nginx.status", {"service": "nginx"}),
        _context(),
    )
    assert result.success is True
    assert tool.calls == [{"service": "nginx"}]


def test_duplicate_tool_name_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        build_agent_assembly(
            audit_dir=tmp_path / "audit",
            tools=[FakeTool("dup.tool"), FakeTool("dup.tool")],
        )


# --------------------------------------------------------------------------
# 红线端到端：装配出来的执行器拦截危险步骤并写磁盘审计链
# --------------------------------------------------------------------------


def test_redline_blocked_end_to_end_with_disk_audit(tmp_path):
    audit_dir = tmp_path / "audit"
    tool = FakeTool("shell.execute", risk_level="HIGH", requires_approval=True)
    assembly = build_agent_assembly(audit_dir=audit_dir, tools=[tool])

    result = assembly.executor.execute(
        PlanStep(1, "清理磁盘", "shell.execute", {"command": "rm -rf /var/log"}),
        _context(),
    )

    assert result.success is False
    assert result.message == "操作被安全基线拦截"
    assert result.metadata["baseline_layer"] == "L2_OPERATIONS"
    assert tool.calls == []  # 红线短路，工具未被调用

    # 审计真实落盘到 tmp_path 且哈希链可验
    assert assembly.baseline.audit_path.exists()
    events = assembly.baseline.audit_sink.events()
    assert [e.event_type for e in events] == ["baseline.redline_hit"]
    report = assembly.verify_audit_chain()
    assert report is not None
    assert report["ok"] is True
    assert report["total_events"] == 1


def test_dag_assembly_fatal_marks_downstream_skipped(tmp_path):
    dangerous = FakeTool("shell.execute", risk_level="HIGH")
    downstream = FakeTool("nginx.status", risk_level="LOW")
    assembly = build_agent_assembly(
        audit_dir=tmp_path / "audit",
        dag=True,
        tools=[dangerous, downstream],
    )

    first = PlanStep(1, "危险步骤", "shell.execute", {"command": "rm -rf /"})
    second = PlanStep(2, "下游步骤", "nginx.status", {}, depends_on=[1])

    plan = assembly.executor.execute_dag([second, first], _context())

    assert plan.status == "aborted_fatal"
    assert dangerous.calls == []
    assert downstream.calls == []
    skipped = [r for r in plan.step_results if r.metadata.get("failure_class") == "skipped"]
    assert len(skipped) == 1
    assert [e.event_type for e in assembly.baseline.audit_sink.events()] == [
        "baseline.redline_hit"
    ]


# --------------------------------------------------------------------------
# 显式关闭基线：纯旧行为回退
# --------------------------------------------------------------------------


def test_security_disabled_falls_back_to_legacy_behavior(tmp_path):
    audit_dir = tmp_path / "audit"
    tool = FakeTool("shell.execute", risk_level="HIGH", requires_approval=True)
    assembly = build_agent_assembly(
        audit_dir=audit_dir, security_enabled=False, tools=[tool]
    )

    # 基线部件全部缺省，且不产生任何审计目录副作用
    assert assembly.baseline is None
    assert assembly.executor.security_engine is None
    assert assembly.verify_audit_chain() is None
    assert not audit_dir.exists()
    assert _voice_tool(assembly.robot_plugin).guard is None

    # 危险命令回到 PolicyEngine 审批链拦截，metadata 不带基线分层
    result = assembly.executor.execute(
        PlanStep(1, "清理", "shell.execute", {"command": "rm -rf /"}),
        _context(),
    )
    assert result.success is False
    assert result.message == "操作被策略阻止"
    assert "baseline_layer" not in result.metadata


def test_robot_guard_can_be_skipped_while_engine_stays_on(tmp_path):
    assembly = build_agent_assembly(
        audit_dir=tmp_path / "audit", with_robot_guard=False
    )

    # 引擎仍在，仅机器人守卫缺省
    assert assembly.executor.security_engine is not None
    assert assembly.baseline.robot_guard is None
    assert _voice_tool(assembly.robot_plugin).guard is None


# --------------------------------------------------------------------------
# fail-closed：审计历史不可信时拒绝重新装配
# --------------------------------------------------------------------------


def test_tampered_history_fails_reassembly_fail_closed(tmp_path):
    audit_dir = tmp_path / "audit"
    tool = FakeTool("shell.execute", risk_level="HIGH")
    first = build_agent_assembly(audit_dir=audit_dir, tools=[tool])
    blocked = first.executor.execute(
        PlanStep(1, "清理", "shell.execute", {"command": "rm -rf /var/log"}),
        _context(),
    )
    assert blocked.success is False
    assert first.baseline.audit_path.exists()

    # 篡改活动行内容但不重算哈希，组合根重新装配必须把 ValueError 透传出来
    payload = json.loads(
        first.baseline.audit_path.read_text(encoding="utf-8").strip()
    )
    payload["decision"] = "TAMPERED"
    first.baseline.audit_path.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    with pytest.raises(ValueError):
        build_agent_assembly(audit_dir=audit_dir)
