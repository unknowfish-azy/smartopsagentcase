"""P3 Orchestrator 核心：任务分解 → 子 Agent 匹配 → 依赖调度 → 结果整合。

核心原则（避免伪多 Agent）：
  1. 每个子 Agent 有独立 system_prompt + 独立 tool_names 白名单
  2. 执行层走 ai-service 的 /api/nn/*（direct mode: 直接 import service；http mode: 真实 HTTP）
  3. 结果整合做冲突检测——不同 Agent 可能给矛盾建议，Orchestrator 必须标注
  4. SubTask.depends_on 是**真实执行约束**：按依赖关系分波并发，上游产物注入下游上下文
  5. 每个子任务带超时隔离与有界重试，单点故障不拖垮整次协同
  6. 一次协同生成唯一 trace_id 与运行指标，支持审计、SLO 统计与问题定位

企业级可靠性约定：
  * 依赖任务失败时，下游默认跳过（skipped），不带着残缺证据继续推理；
  * 超时任务被标记 TIMEOUT 并与其同波其他任务隔离，不影响其他子 Agent 产出；
  * 所有运行状态只挂在本次 OrchestrationPlan 上，不使用跨请求共享状态。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Literal
from uuid import uuid4

from ..kernel.event.bus import EventBus
from ..kernel.event.events import (
    AgentEvent,
    ORCHESTRATION_FINISHED,
    ORCHESTRATION_STARTED,
    ORCHESTRATION_SUBTASK_STARTED,
    ORCHESTRATION_SUBTASK_FINISHED,
)
from ..kernel.registry.registry import KernelRegistry
from .dispatcher import decompose_goal
from .models import (
    AgentProfile,
    AgentSpecialty,
    SubTask,
    SubTaskResult,
    OrchestrationPlan,
)
from .presets import ALL_PRESET_AGENTS, SPECIALTY_INDEX

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorPolicy:
    """多 Agent 协同的运行约束（企业级默认值）。

    max_concurrency       同波并发子 Agent 上限；
    task_timeout_seconds  单波整体预算，超时的子任务被隔离为 TIMEOUT；
    max_task_retries      子任务异常后的额外重试次数（不含首次）；
    retry_backoff_seconds 第 n 次重试等待 n * backoff 秒；
    inject_upstream       是否把上游成功任务的 summary/findings 注入下游 context["upstream"]；
    upstream_char_budget  注入下游的上游证据总字符预算，防止上下文爆炸；
    skip_on_dependency_failure 上游失败时是否跳过下游（fail-closed，默认跳过）；
    sleep_fn              退避等待函数，测试可注入避免真实 sleep。
    """

    max_concurrency: int = 3
    task_timeout_seconds: float = 60.0
    max_task_retries: int = 1
    retry_backoff_seconds: float = 0.0
    inject_upstream: bool = True
    upstream_char_budget: int = 4000
    skip_on_dependency_failure: bool = True
    sleep_fn: Callable[[float], None] = field(default=time.sleep)


class Orchestrator:
    """多 Agent 协同调度器。

    不破坏现有 PlanRunner——PlanRunner 继续做单 Agent 闭环，Orchestrator 在外层协调。
    """

    def __init__(
        self,
        registry: KernelRegistry | None = None,
        event_bus: EventBus | None = None,
        mode: Literal["direct", "http"] = "direct",
        nn_base_url: str = "http://127.0.0.1:8765/api/nn",
        max_concurrency: int = 3,
        executor: Any | None = None,
        policy: OrchestratorPolicy | None = None,
    ) -> None:
        self.registry = registry or KernelRegistry()
        self.event_bus = event_bus or EventBus()
        self.mode = mode
        self.nn_base_url = nn_base_url
        self.policy = policy or OrchestratorPolicy(max_concurrency=max(1, max_concurrency))
        self.max_concurrency = max(1, self.policy.max_concurrency)

        # 执行器可显式注入（测试 / 上层装配）；未注入时按 mode 尝试 direct executor。
        self._direct_executor = (
            executor if executor is not None else self._try_init_direct_executor()
        )

        # 注册预设 Agent Profile
        self._register_presets()

    # ------------------------------------------------------------------
    # 初始化 / 配置
    # ------------------------------------------------------------------

    def _register_presets(self) -> None:
        for profile in ALL_PRESET_AGENTS:
            self.registry.register("agents", profile.agent_id, profile)

    def _try_init_direct_executor(self) -> Any | None:
        """尝试构造 direct mode 执行器——直接 import ai-service 的 service。

        ai-service 不在 sys.path 或 import 失败时返回 None。
        """
        if self.mode != "direct":
            return None
        try:
            import sys
            from pathlib import Path
            ai_service_path = Path(__file__).resolve().parents[2] / "ai-service"
            if str(ai_service_path) not in sys.path:
                sys.path.insert(0, str(ai_service_path))
            from .direct_executor import DirectExecutor
            return DirectExecutor()
        except Exception as exc:
            logger.warning("orchestrator direct executor init failed: %s", exc)
            return None

    def configure(
        self,
        *,
        max_concurrency: int | None = None,
        task_timeout_seconds: float | None = None,
        max_task_retries: int | None = None,
    ) -> "Orchestrator":
        """按请求覆盖运行参数（返回自身，支持链式调用）。"""

        changes: dict[str, Any] = {}
        if task_timeout_seconds is not None:
            changes["task_timeout_seconds"] = max(0.001, float(task_timeout_seconds))
        if max_task_retries is not None:
            changes["max_task_retries"] = max(0, int(max_task_retries))
        if max_concurrency is not None:
            self.max_concurrency = max(1, int(max_concurrency))
            changes["max_concurrency"] = self.max_concurrency
        if changes:
            self.policy = replace(self.policy, **changes)
        return self

    # ------------------------------------------------------------------
    # Agent 注册/查询
    # ------------------------------------------------------------------

    def get_agent(self, agent_id: str) -> AgentProfile | None:
        return self.registry.get("agents", agent_id)

    def list_agents(self, specialty: AgentSpecialty | None = None) -> list[AgentProfile]:
        agents = self.registry.list_category("agents")
        if specialty is not None:
            agents = [a for a in agents if a.specialty == specialty]
        return agents

    def register_agent(self, profile: AgentProfile) -> None:
        self.registry.register("agents", profile.agent_id, profile)

    # ------------------------------------------------------------------
    # 核心：orchestrate
    # ------------------------------------------------------------------

    def orchestrate(
        self,
        goal: str,
        context: dict[str, Any] | None = None,
        enable_agents: list[str] | None = None,
        exclude_agents: list[str] | None = None,
    ) -> OrchestrationPlan:
        """完整协同闭环（同步接口，内部按依赖分波并发执行）。"""

        context = dict(context or {})
        trace_id = uuid4().hex[:16]
        started = time.perf_counter()

        # 1. 任务分解
        subtasks = decompose_goal(goal, context)
        if not subtasks:
            return self._failed_plan(goal, trace_id, "无法分解 goal")

        # 2. 子 Agent 匹配 + 过滤
        matched_tasks = self._match_profiles(subtasks, enable_agents, exclude_agents)
        if not matched_tasks:
            return self._failed_plan(goal, trace_id, "没有可用的子 Agent")

        plan = OrchestrationPlan(goal=goal, subtasks=[t for t, _ in matched_tasks], trace_id=trace_id)
        executor = self._direct_executor
        if executor is None:
            plan.overall_status = "failed"
            plan.final_synthesis = "direct executor 未初始化，ai-service 不可用"
            plan.metrics = self._build_metrics([], started, trace_id, waves=0)
            return plan

        tasks_by_id = {task.task_id: task for task, _ in matched_tasks}
        profiles_by_id = {task.task_id: profile for task, profile in matched_tasks}

        self._emit(
            ORCHESTRATION_STARTED,
            trace_id=trace_id,
            goal=goal,
            task_ids=list(tasks_by_id),
            max_concurrency=self.max_concurrency,
        )

        # 3. 依赖分波执行：同波内并发，波间串行，上游产物注入下游
        results_by_id: dict[str, SubTaskResult] = {}
        pending: list[str] = list(tasks_by_id)
        waves = 0
        while pending:
            ready = [
                task_id
                for task_id in pending
                if all(
                    dep not in tasks_by_id or dep in results_by_id
                    for dep in tasks_by_id[task_id].depends_on
                )
            ]
            if not ready:
                # 依赖成环或依赖永远无法满足：剩余任务全部显式跳过，避免静默丢任务
                for task_id in pending:
                    results_by_id[task_id] = self._skipped_result(
                        tasks_by_id[task_id],
                        profiles_by_id[task_id],
                        f"依赖无法满足（疑似依赖环）: {tasks_by_id[task_id].depends_on}",
                        trace_id,
                    )
                break

            waves += 1
            wave_results = self._run_wave(
                goal, ready, tasks_by_id, profiles_by_id, results_by_id, context, trace_id
            )
            for task_id, result in wave_results.items():
                results_by_id[task_id] = result
                self._emit(
                    ORCHESTRATION_SUBTASK_FINISHED,
                    trace_id=trace_id,
                    task_id=task_id,
                    agent_id=result.agent_id,
                    success=result.success,
                    skipped=result.skipped,
                    error_category=result.error_category,
                    duration_ms=result.duration_ms,
                    attempts=result.attempts,
                )
            pending = [task_id for task_id in pending if task_id not in wave_results]

        # 4. 结果按计划顺序归一 + 冲突检测 + 整合
        order = {task.task_id: index for index, (task, _) in enumerate(matched_tasks)}
        plan.results = sorted(results_by_id.values(), key=lambda r: order.get(r.task_id, 0))
        plan.conflict_notes = self._detect_conflicts(plan.results)
        plan.metrics = self._build_metrics(plan.results, started, trace_id, waves)
        plan.final_synthesis = self._synthesize(goal, plan.results, plan.conflict_notes, plan.metrics)

        succeeded = sum(1 for r in plan.results if r.success)
        if succeeded == len(plan.results) and plan.results:
            plan.overall_status = "completed"
        elif succeeded > 0:
            plan.overall_status = "partial"
        else:
            plan.overall_status = "failed"

        self._emit(
            ORCHESTRATION_FINISHED,
            trace_id=trace_id,
            status=plan.overall_status,
            metrics=plan.metrics,
        )
        return plan

    # ------------------------------------------------------------------
    # 匹配
    # ------------------------------------------------------------------

    @staticmethod
    def _match_profiles(
        subtasks: list[SubTask],
        enable_agents: list[str] | None,
        exclude_agents: list[str] | None,
    ) -> list[tuple[SubTask, AgentProfile]]:
        enabled_set = set(enable_agents) if enable_agents else None
        excluded_set = set(exclude_agents) if exclude_agents else None
        matched: list[tuple[SubTask, AgentProfile]] = []
        for task in subtasks:
            profile = SPECIALTY_INDEX.get(task.required_specialty.value)
            if profile is None:
                logger.warning("no preset agent for specialty=%s, skip task=%s", task.required_specialty, task.task_id)
                continue
            if enabled_set and profile.agent_id not in enabled_set:
                continue
            if excluded_set and profile.agent_id in excluded_set:
                continue
            matched.append((task, profile))
        return matched

    # ------------------------------------------------------------------
    # 分波执行
    # ------------------------------------------------------------------

    def _run_wave(
        self,
        goal: str,
        ready: list[str],
        tasks_by_id: dict[str, SubTask],
        profiles_by_id: dict[str, AgentProfile],
        results_by_id: dict[str, SubTaskResult],
        base_context: dict[str, Any],
        trace_id: str,
    ) -> dict[str, SubTaskResult]:
        """执行一个无依赖冲突的波次：先跳过依赖失败任务，再并发执行其余任务。"""

        outcomes: dict[str, SubTaskResult] = {}
        runnable: list[str] = []

        for task_id in ready:
            task = tasks_by_id[task_id]
            failed_deps = [
                dep
                for dep in task.depends_on
                if dep in results_by_id and not results_by_id[dep].success
            ]
            if failed_deps and self.policy.skip_on_dependency_failure:
                outcomes[task_id] = self._skipped_result(
                    task,
                    profiles_by_id[task_id],
                    f"上游任务未成功，按 fail-closed 跳过: {failed_deps}",
                    trace_id,
                )
            else:
                runnable.append(task_id)

        if not runnable:
            return outcomes

        pool = ThreadPoolExecutor(
            max_workers=min(max(1, self.max_concurrency), len(runnable)),
            thread_name_prefix="orch",
        )
        futures: dict[Future, str] = {}
        try:
            for task_id in runnable:
                task_context = self._task_context(
                    goal, tasks_by_id[task_id], base_context, results_by_id
                )
                futures[
                    pool.submit(
                        self._execute_task,
                        profiles_by_id[task_id],
                        tasks_by_id[task_id],
                        task_context,
                        trace_id,
                    )
                ] = task_id

            deadline = time.perf_counter() + max(0.001, self.policy.task_timeout_seconds)
            for future, task_id in futures.items():
                remaining = max(0.0, deadline - time.perf_counter())
                try:
                    outcomes[task_id] = future.result(timeout=remaining)
                except FutureTimeoutError:
                    future.cancel()
                    logger.warning(
                        "orchestrator.subtask_timeout trace=%s task=%s budget=%.2fs",
                        trace_id, task_id, self.policy.task_timeout_seconds,
                    )
                    outcomes[task_id] = SubTaskResult(
                        task_id=task_id,
                        agent_id=profiles_by_id[task_id].agent_id,
                        success=False,
                        error=f"子任务超过 {self.policy.task_timeout_seconds:.2f}s 预算被隔离",
                        error_category="TIMEOUT",
                        attempts=1,
                        trace_id=trace_id,
                    )
                except Exception as exc:  # noqa: BLE001 - 单个 future 异常不拖垮整波
                    logger.exception("orchestrator.subtask_future_error trace=%s task=%s", trace_id, task_id)
                    outcomes[task_id] = SubTaskResult(
                        task_id=task_id,
                        agent_id=profiles_by_id[task_id].agent_id,
                        success=False,
                        error=f"{type(exc).__name__}: {exc}",
                        error_category="EXECUTION",
                        attempts=1,
                        trace_id=trace_id,
                    )
        finally:
            # 超时线程无法强杀，但不等待，避免单个卡死任务拖垮整次协同。
            pool.shutdown(wait=False, cancel_futures=True)

        return outcomes

    def _execute_task(
        self,
        profile: AgentProfile,
        task: SubTask,
        context: dict[str, Any],
        trace_id: str,
    ) -> SubTaskResult:
        """执行单个子任务，带异常重试；业务失败不重试。"""

        self._emit(
            ORCHESTRATION_SUBTASK_STARTED,
            trace_id=trace_id,
            task_id=task.task_id,
            agent_id=profile.agent_id,
        )
        start = time.perf_counter()
        max_attempts = 1 + max(0, self.policy.max_task_retries)
        attempts = 0
        last_exc: Exception | None = None

        while attempts < max_attempts:
            attempts += 1
            try:
                data = self._direct_executor.execute(profile, task, context) or {}
                if not isinstance(data, dict):
                    raise TypeError(f"executor 返回值必须是 dict，实际为 {type(data).__name__}")
                return SubTaskResult(
                    task_id=task.task_id,
                    agent_id=profile.agent_id,
                    success=True,
                    summary=str(data.get("summary", "")),
                    findings=dict(data.get("findings") or {}),
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    attempts=attempts,
                    trace_id=trace_id,
                )
            except Exception as exc:  # noqa: BLE001 - 子 Agent 异常按失败隔离
                last_exc = exc
                if attempts < max_attempts:
                    backoff = self.policy.retry_backoff_seconds * attempts
                    logger.warning(
                        "orchestrator.subtask_retry trace=%s task=%s agent=%s attempt=%s/%s error=%s",
                        trace_id, task.task_id, profile.agent_id, attempts, max_attempts, exc,
                    )
                    if backoff > 0:
                        self.policy.sleep_fn(backoff)

        logger.exception(
            "orchestrator.subtask_failed trace=%s task=%s agent=%s attempts=%s",
            trace_id, task.task_id, profile.agent_id, attempts,
            exc_info=last_exc,
        )
        return SubTaskResult(
            task_id=task.task_id,
            agent_id=profile.agent_id,
            success=False,
            error=f"{type(last_exc).__name__}: {last_exc}" if last_exc else "未知执行错误",
            error_category="EXECUTION",
            duration_ms=int((time.perf_counter() - start) * 1000),
            attempts=attempts,
            trace_id=trace_id,
        )

    def _task_context(
        self,
        goal: str,
        task: SubTask,
        base_context: dict[str, Any],
        results_by_id: dict[str, SubTaskResult],
    ) -> dict[str, Any]:
        """构造下游任务上下文：基线上游证据注入，受字符预算约束。"""

        if not self.policy.inject_upstream:
            return dict(base_context)

        remaining = self.policy.upstream_char_budget
        upstream: dict[str, Any] = {}
        for dep in task.depends_on:
            result = results_by_id.get(dep)
            if result is None or not result.success or remaining <= 0:
                continue
            summary = result.summary[:400]
            findings = result.findings
            text = json.dumps(findings, ensure_ascii=False, default=str)
            if len(text) > remaining:
                findings = {"_truncated": True, "keys": list(result.findings)[:8]}
                text = json.dumps(findings, ensure_ascii=False, default=str)
            remaining -= len(text) + len(summary)
            upstream[dep] = {
                "agent_id": result.agent_id,
                "summary": summary,
                "findings": findings,
            }

        if not upstream:
            return dict(base_context)

        merged = dict(base_context)
        merged["upstream"] = upstream

        # 案例检索依赖上游证据拼 query：让 depends_on 真正影响检索质量
        if task.required_specialty == AgentSpecialty.CASE_RETRIEVER and not base_context.get("query"):
            heads = "；".join(
                f"{item['agent_id']}: {item['summary']}" for item in upstream.values()
            )
            merged["query"] = f"{goal} | {heads}"[:600]
        return merged

    # ------------------------------------------------------------------
    # 结果构造
    # ------------------------------------------------------------------

    @staticmethod
    def _skipped_result(
        task: SubTask,
        profile: AgentProfile,
        reason: str,
        trace_id: str,
    ) -> SubTaskResult:
        return SubTaskResult(
            task_id=task.task_id,
            agent_id=profile.agent_id,
            success=False,
            skipped=True,
            error=reason,
            error_category="DEPENDENCY",
            attempts=0,
            trace_id=trace_id,
        )

    @staticmethod
    def _failed_plan(goal: str, trace_id: str, reason: str) -> OrchestrationPlan:
        return OrchestrationPlan(
            goal=goal,
            overall_status="failed",
            final_synthesis=reason,
            trace_id=trace_id,
            metrics={
                "trace_id": trace_id,
                "task_count": 0,
                "succeeded": 0,
                "failed": 0,
                "skipped": 0,
                "attempted": 0,
                "retried": 0,
                "timed_out": 0,
                "waves": 0,
                "total_ms": 0,
                "success_rate": 0.0,
            },
        )

    @staticmethod
    def _build_metrics(
        results: list[SubTaskResult],
        started: float,
        trace_id: str,
        waves: int,
    ) -> dict[str, Any]:
        succeeded = sum(1 for r in results if r.success)
        skipped = sum(1 for r in results if r.skipped)
        timed_out = sum(1 for r in results if r.error_category == "TIMEOUT")
        retried = sum(1 for r in results if r.attempts > 1)
        attempted = len(results) - skipped
        return {
            "trace_id": trace_id,
            "task_count": len(results),
            "succeeded": succeeded,
            "failed": len(results) - succeeded - skipped,
            "skipped": skipped,
            "attempted": attempted,
            "retried": retried,
            "timed_out": timed_out,
            "waves": waves,
            "total_ms": int((time.perf_counter() - started) * 1000),
            "success_rate": round(succeeded / len(results), 4) if results else 0.0,
        }

    # ------------------------------------------------------------------
    # 冲突检测 + synthesis
    # ------------------------------------------------------------------

    def _detect_conflicts(self, results: list[SubTaskResult]) -> list[str]:
        """检查子 Agent 结果间的矛盾点（轻量规则，不依赖 LLM）。"""
        notes: list[str] = []
        findings_by_agent = {r.agent_id: r.findings for r in results if r.success}

        # AnomalySleuth 说有 spike，但 RootCauseHunter 说"无显著异常"
        anom = findings_by_agent.get("anomaly-sleuth", {})
        rc = findings_by_agent.get("rootcause-hunter", {})
        anom_spans = anom.get("spans", [])
        rc_confidence = rc.get("confidence", 0.0)
        if anom_spans and rc_confidence < 0.3:
            notes.append(
                "AnomalySleuth 检测到异常 span 但 RootCauseHunter 根因置信度低——"
                "可能是假阳性，建议 LogInterpreter 交叉验证日志"
            )

        # CaseRetriever 找到 resolved 案例但 ActionAdvisor 不推荐相同动作
        cr = findings_by_agent.get("case-retriever", {})
        aa = findings_by_agent.get("action-advisor", {})
        top_case_action = (cr.get("top_resolved_case") or {}).get("action_taken")
        top_advisor_action = (aa.get("top_recommendation") or {}).get("action")
        if top_case_action and top_advisor_action and top_case_action != top_advisor_action:
            notes.append(
                f"历史最佳动作={top_case_action} 与当前 top 推荐={top_advisor_action} 不一致——"
                "需要权衡：历史经验 vs 当前指标"
            )

        return notes

    def _synthesize(
        self,
        goal: str,
        results: list[SubTaskResult],
        conflict_notes: list[str],
        metrics: dict[str, Any],
    ) -> str:
        """把各 Agent 结果整合成一段人类可读的总结（规则，不依赖 LLM）。"""

        parts: list[str] = [f"## 协同目标\n{goal}\n"]

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success and not r.skipped]
        skipped = [r for r in results if r.skipped]

        parts.append(
            "## 执行概览\n"
            f"成功 {len(successes)}/{len(results)}，失败 {len(failures)}，跳过 {len(skipped)}；"
            f"耗时 {metrics.get('total_ms', 0)}ms，波次 {metrics.get('waves', 0)}，"
            f"trace `{metrics.get('trace_id', '')}`\n"
        )

        for r in successes:
            agent_name = SPECIALTY_INDEX.get(_specialty_from_agent_id(r.agent_id), None)
            parts.append(f"### {agent_name.name if agent_name else r.agent_id}")
            if r.summary:
                parts.append(r.summary)
            if r.findings:
                parts.append("```json")
                parts.append(_truncate_json(r.findings))
                parts.append("```")
            parts.append("")

        if failures:
            parts.append("## 失败项")
            for r in failures:
                parts.append(f"- {r.agent_id}: {r.error}（类别 {r.error_category or 'UNKNOWN'}）")
            parts.append("")

        if skipped:
            parts.append("## 跳过项（依赖未满足）")
            for r in skipped:
                parts.append(f"- {r.agent_id}: {r.error}")
            parts.append("")

        if conflict_notes:
            parts.append("## 冲突检测")
            for note in conflict_notes:
                parts.append(f"- ⚠ {note}")
            parts.append("")

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # 事件（同步上下文 best-effort 派发，失败绝不影响主链路）
    # ------------------------------------------------------------------

    def _emit(self, event_name: str, **payload: Any) -> None:
        if self.event_bus is None:
            return
        try:
            if not self.event_bus.has_subscribers(event_name):
                return
            event = AgentEvent(
                name=event_name,
                request_id=payload.get("trace_id"),
                payload=payload,
            )
            coroutine = self.event_bus.publish(event)
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(coroutine)
            else:
                asyncio.get_running_loop().create_task(coroutine)
        except Exception as exc:  # noqa: BLE001 - 观测事件失败不得中断协同
            logger.warning("orchestrator.emit_failed event=%s: %s", event_name, exc)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _specialty_from_agent_id(agent_id: str) -> str:
    for spec_name, profile in SPECIALTY_INDEX.items():
        if profile.agent_id == agent_id:
            return spec_name
    return ""


def _truncate_json(obj: Any, max_chars: int = 800) -> str:
    import json
    try:
        s = json.dumps(obj, ensure_ascii=False, indent=2)
        if len(s) > max_chars:
            return s[:max_chars] + "\n... (truncated)"
        return s
    except Exception:
        return str(obj)[:max_chars]
