"""PlanRunner：规划 → 执行 → 反思 → 重规划 的执行闭环编排（P1）。

把 LLM Planner、Executor（checkpoint/断点续跑）、Reflector 串成
Plan-and-Execute 闭环。反思重规划次数有硬上限，防止"越规划越发散"。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import uuid4

from agent.executor.executor import ExecutionPolicy, PlanExecutionResult
from agent.reflection.reflection import ReflectionVerdict, Reflector

logger = logging.getLogger(__name__)


@dataclass
class RunOutcome:
    """一次完整闭环的产出。"""

    goal: str
    success: bool
    status: str = "completed"  # completed / failed / reflection_budget_exhausted
    reason: str | None = None
    plan_ids: list[str] = field(default_factory=list)
    plan_results: list[PlanExecutionResult] = field(default_factory=list)
    reflections: list[ReflectionVerdict] = field(default_factory=list)
    planner_used: str = "rule"

    @property
    def final_result(self) -> PlanExecutionResult | None:
        return self.plan_results[-1] if self.plan_results else None

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "success": self.success,
            "status": self.status,
            "plan_ids": self.plan_ids,
            "planner_used": self.planner_used,
            "reflections": [
                {
                    "decision": v.decision,
                    "reason": v.reason,
                    "failed_step_ids": v.failed_step_ids,
                    "source": v.source,
                }
                for v in self.reflections
            ],
            "plans": [result.to_dict() for result in self.plan_results],
        }


class PlanRunner:
    """执行闭环编排器。

    每一轮：规划（LLM 优先，失败降级规则）→ checkpoint 执行 → 反思评审；
    评审为 replan 且轮次预算未耗尽时，携带失败上下文重新规划再执行。
    """

    def __init__(
        self,
        planner,
        executor,
        reflector: Reflector | None = None,
        plan_store=None,
        event_stream=None,
        max_execution_rounds: int = 3,
        experience_sink=None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.reflector = reflector or Reflector()
        self.plan_store = plan_store
        # P4：可选事件溯源流（agent/planner/events.py 的 EventStream）
        self.event_stream = event_stream
        # P5：可选失败复盘沉淀（agent/planner/experience.py 的 ExperienceSink）
        self.experience_sink = experience_sink
        self.max_execution_rounds = max(1, max_execution_rounds)

    def run(
        self,
        goal: str,
        context,
        execution_policy: ExecutionPolicy | None = None,
        failure_context: str | None = None,
    ) -> RunOutcome:
        outcome = RunOutcome(goal=goal, success=False)

        for round_index in range(self.max_execution_rounds):
            plan = self.planner.create_plan(goal, failure_context=failure_context)
            outcome.planner_used = plan.planner

            plan_id = f"{uuid4().hex[:12]}-r{round_index + 1}"
            outcome.plan_ids.append(plan_id)

            steps = plan.steps
            if self.plan_store is not None:
                self.plan_store.create(plan_id, goal, steps)
            if self.event_stream is not None:
                self.event_stream.append(
                    "plan_created",
                    plan_id=plan_id,
                    round=round_index + 1,
                    planner=plan.planner,
                    step_count=len(steps),
                )

            result = self.executor.execute_plan(
                steps,
                context,
                policy=execution_policy,
                plan_store=self.plan_store,
                plan_id=plan_id if self.plan_store is not None else None,
            )
            outcome.plan_results.append(result)
            if self.event_stream is not None:
                self.event_stream.append(
                    "plan_finished", plan_id=plan_id, status=result.status, success=result.success
                )
            logger.info(
                "runner.round round=%s plan_id=%s status=%s planner=%s",
                round_index + 1, plan_id, result.status, plan.planner,
            )

            if result.success:
                outcome.success = True
                outcome.status = "completed"
                if self.event_stream is not None:
                    self.event_stream.append("run_finished", status="completed")
                return outcome

            # 失败 → 反思评审
            verdict = self.reflector.review(goal, result)
            outcome.reflections.append(verdict)
            if self.event_stream is not None:
                self.event_stream.append(
                    "reflection", decision=verdict.decision, reason=verdict.reason
                )

            if verdict.decision != "replan":
                outcome.status = "failed"
                outcome.reason = f"评审不通过且无需重规划: {verdict.reason}"
                if self.event_stream is not None:
                    self.event_stream.append("run_finished", status="failed")
                self._report_failure(outcome, context)
                return outcome

            # 携带失败上下文重规划（最后一轮预算耗尽则直接结束）
            failure_context = (
                f"第 {round_index + 1} 轮失败步骤: {verdict.failed_step_ids}；"
                f"原因: {verdict.reason}"
            )

        outcome.status = "reflection_budget_exhausted"
        outcome.reason = (
            f"重规划轮次达到上限 {self.max_execution_rounds}，仍未完成，需人工介入"
        )
        if self.event_stream is not None:
            self.event_stream.append("run_finished", status=outcome.status)
        self._report_failure(outcome, context)
        return outcome

    def _report_failure(self, outcome: RunOutcome, context) -> None:
        """失败终态时把教训交给可选的复盘沉淀 sink（fail-open，见 experience.py）。"""
        if self.experience_sink is None:
            return
        try:
            callback = getattr(self.experience_sink, "on_run_finished", None)
            if callback is not None:
                callback(outcome, context)
            else:
                self.experience_sink.report(outcome, getattr(context, "user_id", None))
        except Exception as exc:  # noqa: BLE001 - 复盘上报绝不阻塞执行链路
            logger.warning(
                "runner.experience_sink failed plan_id=%s: %s",
                outcome.plan_ids[-1] if outcome.plan_ids else "-", exc,
            )


__all__ = [
    "PlanRunner",
    "RunOutcome",
]
