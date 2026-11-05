import pytest

from agent.planner.planner import AgentPlanner


@pytest.mark.parametrize("goal,service", [
    ("重启 nginx", "nginx"), ("重启 mysql", "mysql"), ("重启redis服务", "redis"),
    ("restart MYSQL", "mysql"), ("请帮我重启 mysql.service", "mysql"),
    ("mysql 服务重启", "mysql"),
])
def test_restart_binds_the_explicit_target(goal, service):
    plan = AgentPlanner().create_plan(goal)
    assert len(plan.steps) == 1
    step = plan.steps[0]
    assert step.tool_name == "server.restart"
    assert step.arguments == {"service": service}
    assert service in step.action
    assert step.requires_approval is True
    assert plan.requires_human_approval is True


@pytest.mark.parametrize("goal", [
    "重启服务", "重启 postgresql", "重启 nginx 和 mysql", "不要重启 nginx",
    "don't restart mysql", "重启 mysql; shutdown", "restart mysqlbackup",
    "先查看 nginx 状态再重启 mysql", "mysql restart && redis restart", "restartmysql", "nginxstatus",
    "restartmysql.service", "mysql.servicerestart",
])
def test_unknown_or_ambiguous_request_never_guesses_a_write_target(goal):
    plan = AgentPlanner().create_plan(goal)
    assert [step.tool_name for step in plan.steps] == ["knowledge.search"]
    assert plan.steps[0].arguments == {"query": goal}
    assert plan.requires_human_approval is False


@pytest.mark.parametrize("goal,service", [("检查 nginx 状态", "nginx"), ("mysql status", "mysql"), ("查看redis服务状态", "redis")])
def test_status_query_is_read_only_and_binds_target(goal, service):
    plan = AgentPlanner().create_plan(goal)
    assert plan.steps[0].tool_name == "server.status"
    assert plan.steps[0].arguments == {"service": service}
    assert plan.requires_human_approval is False
