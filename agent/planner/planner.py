from uuid import uuid4

from .models import AgentPlan
from .steps import PlanStep


class AgentPlanner:
    """
    基础规则 Planner。

    当前阶段不强制依赖 LLM。
    后续可以把这里替换成 LLM Planner。
    """

    def create_plan(
        self,
        goal: str,
    ) -> AgentPlan:

        request_id = str(uuid4())

        steps = []

        goal_lower = goal.lower()

        if (
            "nginx" in goal_lower
            and (
                "状态" in goal
                or "status" in goal_lower
            )
        ):
            steps.append(
                PlanStep(
                    step_id=1,
                    action="检查 nginx 状态",
                    tool_name="server.status",
                    arguments={
                        "service": "nginx"
                    },
                    description=(
                        "读取 nginx 当前运行状态"
                    ),
                )
            )

        elif (
            "重启" in goal
            or "restart" in goal_lower
        ):
            steps.append(
                PlanStep(
                    step_id=1,
                    action="重启服务",
                    tool_name="server.restart",
                    arguments={
                        "service": "nginx"
                    },
                    description=(
                        "重启指定服务"
                    ),
                    requires_approval=True,
                )
            )

        else:
            steps.append(
                PlanStep(
                    step_id=1,
                    action="查询知识库",
                    tool_name="knowledge.search",
                    arguments={
                        "query": goal
                    },
                    description=(
                        "从知识库检索相关运维知识"
                    ),
                )
            )

        return AgentPlan(
            request_id=request_id,
            goal=goal,
            steps=steps,
            requires_human_approval=any(
                step.requires_approval
                for step in steps
            ),
        )