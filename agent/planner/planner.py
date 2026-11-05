import re
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

        goal_lower = re.sub(r"^(?:请帮我|帮我|请)\s*", "", goal.strip().lower()).rstrip("。！!?").strip()
        service = r"(nginx|mysql|redis)(?:\.service)?"
        restart = re.fullmatch(
            rf"重启(?:一下)?\s*(?:服务\s*)?{service}(?:\s*服务)?|restart\s+{service}|{service}(?:\s*服务)?\s*重启|{service}\s+restart",
            goal_lower,
        )
        status = re.fullmatch(
            rf"(?:检查|查看|查询)\s*{service}(?:\s*服务)?\s*状态|{service}(?:\s*服务)?\s*状态|{service}\s+status|status\s+{service}",
            goal_lower,
        )

        if status:
            target = next(group for group in status.groups() if group is not None)
            steps.append(
                PlanStep(
                    step_id=1,
                    action=f"检查 {target} 状态",
                    tool_name="server.status",
                    arguments={
                        "service": target
                    },
                    description=(
                        f"读取 {target} 当前运行状态"
                    ),
                )
            )

        elif restart:
            target = next(group for group in restart.groups() if group is not None)
            steps.append(
                PlanStep(
                    step_id=1,
                    action=f"重启 {target}",
                    tool_name="server.restart",
                    arguments={
                        "service": target
                    },
                    description=(
                        f"重启明确指定的 {target} 服务"
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
