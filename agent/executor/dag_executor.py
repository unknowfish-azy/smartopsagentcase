"""DAG 执行器（P3，蒸馏 AgentForge 的"按依赖调度 + 并发上限"）。

与线性 execute_plan 的关系：
* 复用同一个 AgentExecutor.execute()（参数校验 / 授权 / 超时 / 重试 / 失败分级）；
* 上层调度改为 Kahn 分波：波内并行（受并发上限控制），波间按依赖串行；
* 失败语义对齐 P0：fatal → 下游全部标记 skipped 并终止；
  recoverable → 记录后继续（其下游仍执行，由上层反思/重规划决策）；
* checkpoint 落盘复用 plan_store.record_step（线性 resume 不感知 DAG，
  DAG 断点续跑属 P4 事件溯源范畴）。

线程模型：波内用 ThreadPoolExecutor 并行执行同步单步；每步仍是
Executor 的同步契约（单步内部已有自己的超时线程），不会嵌套阻塞。
"""

from __future__ import annotations

import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from agent.executor.executor import AgentExecutor, ExecutionPolicy, PlanExecutionResult
from agent.executor.result import ExecutionResult

from agent.planner.dag import topological_waves

logger = logging.getLogger(__name__)


class DagExecutor(AgentExecutor):
    """在 AgentExecutor 之上增加依赖调度与并发控制的执行器。"""

    def execute_dag(
        self,
        steps,
        context,
        policy: ExecutionPolicy | None = None,
        plan_store=None,
        plan_id: str | None = None,
        max_concurrency: int = 3,
    ) -> PlanExecutionResult:
        policy = policy or self.execution_policy
        context = deepcopy(context)
        plan_result = PlanExecutionResult(status="completed")

        waves = topological_waves(list(steps))
        if waves is None:
            # 环 / step_id 冲突：退回线性执行（AgentForge 的降级语义）
            logger.warning("dag_executor invalid graph -> linear fallback")
            return self.execute_plan(
                list(steps), context, policy=policy,
                plan_store=plan_store, plan_id=plan_id,
            )

        fingerprints: deque[str] = deque(maxlen=policy.loop_window)
        failed_ids: set[int] = set()
        executed = 0

        for wave_index, wave in enumerate(waves):
            remaining_budget = policy.max_rounds - executed
            if remaining_budget <= 0:
                plan_result.status = "max_rounds_exceeded"
                plan_result.reason = f"达到最大轮次上限 {policy.max_rounds}"
                break
            wave = wave[:remaining_budget]

            # 波内并行执行（并发上限控制）
            batch = wave[: max(1, max_concurrency)]
            if len(batch) > 1:
                with ThreadPoolExecutor(max_workers=len(batch)) as pool:
                    results = list(pool.map(
                        lambda s: self.execute(deepcopy(s), context), batch,
                    ))
            else:
                results = [self.execute(deepcopy(batch[0]), context)]
            executed += len(batch)

            for step, step_result in zip(batch, results):
                step_result.metadata["step_id"] = step.step_id
                step_result.metadata["wave"] = wave_index
                plan_result.step_results.append(step_result)

                if plan_store is not None and plan_id:
                    plan_store.record_step(
                        plan_id, step.step_id,
                        success=step_result.success,
                        error_category=step_result.error_category,
                        error=step_result.error,
                    )

                if step_result.success:
                    continue

                failed_ids.add(step.step_id)
                fingerprint = self._fingerprint(step)
                fingerprints.append(fingerprint)
                if fingerprints.count(fingerprint) >= policy.loop_threshold:
                    plan_result.status = "aborted_loop"
                    plan_result.reason = (
                        f"检测到死循环: 工具 {step.tool_name} 相同参数在最近 "
                        f"{policy.loop_window} 步内重复失败 {policy.loop_threshold} 次"
                    )
                    self._mark_downstream_skipped(plan_result, steps, failed_ids)
                    if plan_store is not None and plan_id:
                        plan_store.finish(plan_id, plan_result.status)
                    return plan_result

                if step_result.metadata.get("failure_class") == "fatal":
                    plan_result.status = "aborted_fatal"
                    plan_result.reason = (
                        f"步骤 {step.step_id} ({step.tool_name}) 致命失败 "
                        f"[{step_result.error_category}]: {step_result.error}"
                    )
                    self._mark_downstream_skipped(plan_result, steps, failed_ids)
                    if plan_store is not None and plan_id:
                        plan_store.finish(plan_id, plan_result.status)
                    return plan_result

                logger.warning(
                    "dag_executor.step_recoverable step_id=%s tool=%s category=%s",
                    step.step_id, step.tool_name, step_result.error_category,
                )

            if len(batch) < len(wave):
                # 并发上限截断了本波，剩余步骤放回下一轮处理
                rest = wave[len(batch):]
                waves.insert(wave_index + 1, rest)

        if plan_result.status == "completed" and plan_result.reason is None:
            plan_result.reason = f"DAG 全部 {len(plan_result.step_results)} 步执行完毕"

        if plan_store is not None and plan_id:
            plan_store.finish(plan_id, plan_result.status)

        return plan_result

    @staticmethod
    def _mark_downstream_skipped(
        plan_result: PlanExecutionResult, steps: list, failed_ids: set[int],
    ) -> None:
        """fatal/死循环终止后，把所有未执行的下游步骤标记为 skipped 记录。"""

        by_id = {s.step_id: s for s in steps}
        executed_ids = {r.metadata.get("step_id") for r in plan_result.step_results}
        blocked_by: dict[int, set[int]] = {}
        for step in steps:
            if step.step_id in executed_ids:
                continue
            failed_deps = set(step.depends_on) & failed_ids
            if failed_deps:
                blocked_by[step.step_id] = failed_deps
        for sid in sorted(blocked_by):
            plan_result.step_results.append(ExecutionResult(
                success=False,
                tool_name=by_id[sid].tool_name,
                message="上游失败，步骤跳过",
                error=f"SKIPPED_BY_UPSTREAM_FAILURE: 依赖步骤 {sorted(blocked_by[sid])} 失败",
                metadata={
                    "step_id": sid,
                    "failure_class": "skipped",
                    "attempts": 0,
                },
            ))


__all__ = ["DagExecutor"]
