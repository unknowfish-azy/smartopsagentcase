"""垂直子智能体基类（日志诊断 / 巡检）。

设计约束（复用现有 DAG 与工具注册表，不新建编排框架）：

1. 子智能体只负责产出预置的 DAG 模板（``PlanStep`` 列表），
   执行仍由 ``agent.executor`` 的 AgentExecutor / DagExecutor 完成；
2. 计划合法性复用 ``agent.planner.dag.validate_dag``，
   波次调度复用 ``topological_waves``，不重复实现；
3. 子智能体声明的工具必须在 ``ToolRegistry`` 中注册过，
   未注册的步骤在生成计划时被剔除并重排依赖，绝不虚构能力；
4. ``SubAgentPlanner`` 与 ``LLMPlanner.create_plan`` 签名一致，
   可直接替换进 ``PlanRunner(planner=...)``；未命中时原样委托给原规划器。
"""

from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass

from agent.planner.dag import validate_dag
from agent.planner.models import AgentPlan
from agent.planner.steps import PlanStep

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubAgentSpec:
    """子智能体能力声明：名称、职责、触发关键词、依赖工具。"""

    name: str
    title: str
    description: str
    keywords: tuple[str, ...] = ()
    tool_names: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "keywords": list(self.keywords),
            "tool_names": list(self.tool_names),
        }


class SubAgent:
    """垂直子智能体基类：匹配目标 → 产出预置 DAG 模板。"""

    spec: SubAgentSpec

    @property
    def name(self) -> str:
        return self.spec.name

    # ------------------------------------------------------------------
    # 匹配
    # ------------------------------------------------------------------

    def match_hits(self, goal: str) -> list[str]:
        """返回目标文本命中的关键词（大小写不敏感）。"""

        text = (goal or "").lower()
        if not text.strip():
            return []
        return [keyword for keyword in self.spec.keywords if keyword.lower() in text]

    def match_score(self, goal: str) -> float:
        """命中关键词条数即得分；0 表示不匹配。"""

        return float(len(self.match_hits(goal)))

    # ------------------------------------------------------------------
    # 计划
    # ------------------------------------------------------------------

    def build_steps(self, goal: str) -> list[PlanStep]:
        """子类实现：产出预置 DAG 模板（step_id 从 1 开始连续编号）。"""

        raise NotImplementedError

    def plan(self, goal: str, tool_registry=None) -> AgentPlan:
        """生成子智能体计划：按工具注册表过滤 → 重排 → DAG 校验。"""

        steps = self.build_steps(goal)
        dropped: list[str] = []

        if tool_registry is not None:
            steps, dropped = _keep_available(steps, tool_registry)

        metadata: dict = {
            "subagent": self.spec.name,
            "subagent_title": self.spec.title,
        }
        if dropped:
            metadata["dropped_tools"] = sorted(set(dropped))

        if not steps:
            metadata["reason"] = "没有可用工具，子智能体无法产出步骤"
            return AgentPlan(
                request_id=(goal or "")[:32],
                goal=goal,
                steps=[],
                planner=f"subagent:{self.spec.name}",
                metadata=metadata,
            )

        validation = validate_dag(steps)
        if not validation.ok:
            metadata["dag_problems"] = list(validation.problems)

        return AgentPlan(
            request_id=(goal or "")[:32],
            goal=goal,
            steps=steps,
            requires_human_approval=any(step.requires_approval for step in steps),
            planner=f"subagent:{self.spec.name}",
            metadata=metadata,
        )


def _keep_available(steps: list[PlanStep], tool_registry) -> tuple[list[PlanStep], list[str]]:
    """剔除注册表里没有的工具体，并把 step_id / depends_on 重排为连续编号。"""

    available: list[PlanStep] = []
    dropped: list[str] = []
    for step in steps:
        if tool_registry.get(step.tool_name) is None:
            dropped.append(step.tool_name)
        else:
            available.append(step)

    if not dropped:
        return steps, []

    id_map = {step.step_id: index for index, step in enumerate(available, start=1)}
    remapped: list[PlanStep] = []
    for new_id, step in enumerate(available, start=1):
        remapped.append(
            PlanStep(
                step_id=new_id,
                action=step.action,
                tool_name=step.tool_name,
                arguments=dict(step.arguments),
                description=step.description,
                requires_approval=step.requires_approval,
                depends_on=[id_map[dep] for dep in step.depends_on if dep in id_map],
            )
        )
    return remapped, dropped


class SubAgentRegistry:
    """子智能体注册表：按命中关键词条数选择最匹配的一个。"""

    def __init__(self, agents: list[SubAgent] | None = None) -> None:
        self._agents: dict[str, SubAgent] = {}
        for agent in agents or ():
            self.register(agent)

    def register(self, agent: SubAgent) -> None:
        if not agent.spec.name:
            raise ValueError("子智能体必须定义 spec.name")
        self._agents[agent.spec.name] = agent

    def unregister(self, name: str) -> None:
        self._agents.pop(name, None)

    def get(self, name: str) -> SubAgent | None:
        return self._agents.get(name)

    def list(self) -> list[SubAgent]:
        return list(self._agents.values())

    def match(self, goal: str, min_hits: int = 1) -> tuple[SubAgent, float] | None:
        """返回 (子智能体, 命中条数)；同分按注册顺序取先注册者，保证确定性。"""

        best: tuple[SubAgent, float] | None = None
        for agent in self._agents.values():
            score = agent.match_score(goal)
            if score < max(1, min_hits):
                continue
            if best is None or score > best[1]:
                best = (agent, score)
        return best


class SubAgentPlanner:
    """子智能体优先的规划器，未命中时委托给原规划器（LLM / 规则）。

    与 ``LLMPlanner.create_plan(goal, failure_context=None)`` 签名一致，
    可直接替换进 ``PlanRunner``，不改变执行与反思链路。
    """

    def __init__(
        self,
        fallback_planner,
        registry: SubAgentRegistry | None = None,
        tool_registry=None,
        min_hits: int = 1,
    ) -> None:
        self.fallback_planner = fallback_planner
        self.registry = registry
        self.tool_registry = tool_registry
        self.min_hits = min_hits
        self._fallback_accepts_context = _accepts_failure_context(fallback_planner)

    def create_plan(self, goal: str, failure_context: str | None = None) -> AgentPlan:
        matched = (
            self.registry.match(goal, min_hits=self.min_hits)
            if self.registry is not None
            else None
        )

        if matched is not None:
            agent, hits = matched
            plan = agent.plan(goal, self.tool_registry)
            if plan.steps:
                plan.metadata["match_hits"] = hits
                logger.info(
                    "planner.subagent hit=%s goal=%s steps=%s",
                    agent.name, goal, len(plan.steps),
                )
                return plan
            logger.warning(
                "planner.subagent matched %s but no available tools -> fallback", agent.name
            )

        if self._fallback_accepts_context:
            return self.fallback_planner.create_plan(goal, failure_context=failure_context)
        return self.fallback_planner.create_plan(goal)


def _accepts_failure_context(planner) -> bool:
    """判断 fallback 规划器是否接受 failure_context（规则 Planner 不接受）。"""

    try:
        parameters = inspect.signature(planner.create_plan).parameters
    except (TypeError, ValueError):
        return False
    return "failure_context" in parameters


__all__ = [
    "SubAgentSpec",
    "SubAgent",
    "SubAgentRegistry",
    "SubAgentPlanner",
]
