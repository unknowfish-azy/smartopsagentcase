"""子智能体测试：日志诊断 / 巡检的匹配、预置 DAG、工具过滤与规划器委托。"""

import pytest

from agent.planner.dag import topological_waves, validate_dag
from agent.planner.models import AgentPlan
from agent.subagents import (
    LogDiagnosisAgent,
    PatrolAgent,
    SubAgentPlanner,
    default_registry,
)
from agent.tools.registry import ToolRegistry

LOG_TOOLS = (
    "docker.logs", "nginx.logs", "nginx.status",
    "mysql.status", "redis.info", "knowledge.search",
)
PATROL_TOOLS = (
    "nginx.status", "nginx.config_test", "mysql.status",
    "redis.info", "redis.memory", "docker.ps",
)


class _NamedTool:
    """只用于 ToolRegistry 占位的最小工具。"""

    def __init__(self, name: str) -> None:
        self.name = name


def _registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(_NamedTool(name))
    return registry


# ---------------------------------------------------------------------------
# 匹配
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("goal", [
    "帮我分析一下 nginx 日志",
    "服务报错 502 了，排查一下",
    "backend 容器 error 一堆",
])
def test_log_goal_matches_log_diagnosis(goal):
    matched = default_registry().match(goal)
    assert matched is not None
    agent, hits = matched
    assert agent.name == "log_diagnosis"
    assert hits >= 1


@pytest.mark.parametrize("goal", [
    "给系统做一次巡检",
    "来个全面检查",
    "看看所有服务的健康检查",
    "patrol please",
])
def test_patrol_goal_matches_patrol(goal):
    matched = default_registry().match(goal)
    assert matched is not None
    agent, hits = matched
    assert agent.name == "patrol"
    assert hits >= 1


def test_simple_status_query_does_not_hit_subagents():
    # 单服务状态查询仍由 AgentPlanner 的单步语义处理
    assert default_registry().match("检查 nginx 状态") is None


def test_empty_goal_never_matches():
    assert default_registry().match("") is None


# ---------------------------------------------------------------------------
# 日志诊断预置 DAG
# ---------------------------------------------------------------------------


def test_log_plan_is_valid_two_wave_dag():
    plan = LogDiagnosisAgent().plan("nginx 报错 502", _registry(*LOG_TOOLS))

    assert plan.planner == "subagent:log_diagnosis"
    assert [step.tool_name for step in plan.steps] == [
        "docker.logs", "nginx.logs", "nginx.status", "knowledge.search",
    ]
    assert plan.steps[3].depends_on == [1, 2, 3]
    assert plan.requires_human_approval is False
    assert validate_dag(plan.steps).ok

    waves = topological_waves(plan.steps)
    assert [len(wave) for wave in waves] == [3, 1]


def test_log_plan_binds_service_and_container_from_goal():
    plan = LogDiagnosisAgent().plan("mysql 容器 smartops-db 报错", _registry(*LOG_TOOLS))

    assert plan.steps[0].arguments == {"container": "smartops-db", "tail": 300}
    assert plan.steps[2].tool_name == "mysql.status"
    assert "mysql" in plan.steps[2].action


def test_log_plan_defaults_to_nginx_and_backend_container():
    plan = LogDiagnosisAgent().plan("报错了", _registry(*LOG_TOOLS))

    assert plan.steps[0].arguments["container"] == "smartops-backend"
    assert plan.steps[2].tool_name == "nginx.status"


def test_log_plan_uses_redis_info_for_redis_target():
    plan = LogDiagnosisAgent().plan("redis 异常", _registry(*LOG_TOOLS))

    assert plan.steps[2].tool_name == "redis.info"
    assert plan.steps[2].arguments == {"section": "memory"}


# ---------------------------------------------------------------------------
# 巡检预置 DAG
# ---------------------------------------------------------------------------


def test_patrol_steps_are_readonly_and_parallel():
    plan = PatrolAgent().plan("做一次巡检", _registry(*PATROL_TOOLS))

    assert plan.planner == "subagent:patrol"
    assert {step.tool_name for step in plan.steps} == set(PATROL_TOOLS)
    assert all(step.requires_approval is False for step in plan.steps)
    assert all(not step.depends_on for step in plan.steps)
    assert validate_dag(plan.steps).ok
    assert len(topological_waves(plan.steps)) == 1


# ---------------------------------------------------------------------------
# 工具注册表过滤
# ---------------------------------------------------------------------------


def test_missing_tools_are_dropped_and_ids_remapped():
    plan = LogDiagnosisAgent().plan("nginx 报错", _registry("nginx.logs"))

    assert len(plan.steps) == 1
    assert plan.steps[0].step_id == 1
    assert plan.steps[0].tool_name == "nginx.logs"
    assert plan.steps[0].depends_on == []
    assert plan.metadata["dropped_tools"] == sorted(
        {"docker.logs", "nginx.status", "knowledge.search"}
    )


def test_dependency_is_remapped_after_filtering():
    plan = LogDiagnosisAgent().plan(
        "nginx 报错", _registry("nginx.logs", "knowledge.search")
    )

    assert [step.step_id for step in plan.steps] == [1, 2]
    assert plan.steps[1].tool_name == "knowledge.search"
    assert plan.steps[1].depends_on == [1]
    assert validate_dag(plan.steps).ok


def test_no_available_tool_yields_empty_plan():
    plan = PatrolAgent().plan("巡检", _registry())

    assert plan.steps == []
    assert plan.planner == "subagent:patrol"
    assert plan.metadata["reason"]


# ---------------------------------------------------------------------------
# SubAgentPlanner：命中优先，未命中委托
# ---------------------------------------------------------------------------


class _RuleFallback:
    """模拟 AgentPlanner：不接受 failure_context。"""

    def __init__(self) -> None:
        self.calls = []

    def create_plan(self, goal):
        self.calls.append(goal)
        return AgentPlan(request_id="fallback", goal=goal, planner="rule")


class _ContextFallback:
    """模拟 LLMPlanner：接受 failure_context。"""

    def __init__(self) -> None:
        self.contexts = []

    def create_plan(self, goal, failure_context=None):
        self.contexts.append(failure_context)
        return AgentPlan(request_id="fallback", goal=goal, planner="llm")


def test_planner_prefers_subagent_when_tools_ready():
    fallback = _RuleFallback()
    planner = SubAgentPlanner(
        fallback, registry=default_registry(), tool_registry=_registry(*LOG_TOOLS)
    )

    plan = planner.create_plan("帮我分析 nginx 日志")

    assert plan.planner == "subagent:log_diagnosis"
    assert plan.metadata["match_hits"] >= 1
    assert fallback.calls == []


def test_planner_delegates_when_no_subagent_matches():
    fallback = _RuleFallback()
    planner = SubAgentPlanner(
        fallback, registry=default_registry(), tool_registry=_registry(*LOG_TOOLS)
    )

    plan = planner.create_plan("帮我写一段自我介绍")

    assert plan.planner == "rule"
    assert fallback.calls == ["帮我写一段自我介绍"]


def test_planner_delegates_when_matched_but_tools_missing():
    fallback = _RuleFallback()
    planner = SubAgentPlanner(
        fallback, registry=default_registry(), tool_registry=_registry()
    )

    plan = planner.create_plan("帮我分析 nginx 日志")

    assert plan.planner == "rule"
    assert fallback.calls == ["帮我分析 nginx 日志"]


def test_planner_passes_failure_context_to_capable_fallback():
    fallback = _ContextFallback()
    planner = SubAgentPlanner(fallback, registry=default_registry())

    plan = planner.create_plan("换个话题", failure_context="第 1 轮失败步骤: [1]")

    assert plan.planner == "llm"
    assert fallback.contexts == ["第 1 轮失败步骤: [1]"]
