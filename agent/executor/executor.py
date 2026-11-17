import asyncio
import inspect
import json
import logging
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.runtime_events import RunIdentity, terminal_event
from agent.sdk.tool import ImplementationStatus
from agent.tools.errors import (
    FAILURE_GRADE,
    ToolErrorCategory,
    ToolExecutionError,
    classify_exception,
)
from agent.tools.validation import truncate_output, validate_arguments

from .audit import AuditRecord
from .models import ExecutionContext
from .result import ExecutionResult

logger = logging.getLogger(__name__)


@dataclass
class ExecutionPolicy:
    """执行闭环控制参数（P0 加固）。

    max_rounds      单个计划的最大执行轮次，防止规划爆炸；
    max_retries     单步额外重试次数（仅限可重试错误 + 幂等工具）；
    backoff_base    指数退避基数，第 n 次重试等待 base * 2^(n-1) 秒；
    loop_window     死循环检测的指纹滑动窗口大小；
    loop_threshold  窗口内同一动作指纹出现次数上限，超过即判定死循环；
    default_step_timeout_ms 未声明 deadline 的工具的单步超时；
    sleep_fn        退避等待函数，测试可注入避免真实 sleep。
    """

    max_rounds: int = 12
    max_retries: int = 2
    backoff_base_seconds: float = 0.5
    loop_window: int = 6
    loop_threshold: int = 3
    default_step_timeout_ms: int = 30_000
    sleep_fn: Callable[[float], None] = field(default=time.sleep)


@dataclass
class PlanExecutionResult:
    """多步计划执行结果（含失败分级与终止原因）。"""

    status: str  # completed / aborted_fatal / aborted_loop / max_rounds_exceeded
    step_results: list[ExecutionResult] = field(default_factory=list)
    reason: str | None = None

    @property
    def success(self) -> bool:
        # 整体成功 = 走完所有步骤且每一步都成功；
        # 有 recoverable 失败时 status 是 completed，但不算整体成功（触发反思/重规划）。
        return self.status == "completed" and all(r.success for r in self.step_results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "reason": self.reason,
            "steps": [
                {
                    "step_id": r.metadata.get("step_id"),
                    "tool_name": r.tool_name,
                    "success": r.success,
                    "error_category": r.error_category,
                    "failure_class": r.metadata.get("failure_class"),
                    "attempts": r.metadata.get("attempts"),
                }
                for r in self.step_results
            ],
        }


class AgentExecutor:
    """
    Agent 工具执行器。

    Executor 不负责决定执行什么。
    执行计划由 Planner 负责生成，
    是否允许执行由 Policy Engine 决定。

    P0 执行闭环加固：
    * 参数校验（input_schema）+ 输出预算截断；
    * 单步超时 + 重试指数退避（仅幂等工具的可重试错误）；
    * 计划级最大轮次、死循环检测、失败分级（重试/换方案/终止上报）。
    """

    def __init__(
        self,
        tool_registry,
        policy_engine,
        execution_policy: ExecutionPolicy | None = None,
        security_engine=None,
    ):
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.execution_policy = execution_policy or ExecutionPolicy()
        # 安全基线引擎为可选依赖：未挂载时执行链行为与历史完全一致。
        # 挂载后 L0 合规/L2 红线/L1 限流在 PolicyEngine 授权之前短路。
        self.security_engine = security_engine
        self.audit_records: list[
            AuditRecord
        ] = []
        self._run_events = []

    # ------------------------------------------------------------------
    # 单步执行入口（保持向后兼容）
    # ------------------------------------------------------------------

    def execute(
        self,
        step,
        context: ExecutionContext,
    ) -> ExecutionResult:
        step, context = deepcopy(step), deepcopy(context)
        identity = RunIdentity.create(request_id=context.request_id, task_id=context.task_id, run_id=context.run_id)
        event = terminal_event(identity, "executor", "started", step_id=step.step_id)
        result = self._execute(step, context, event)
        status = "dry_run" if result.success and context.dry_run else "succeeded" if result.success else "failed"
        if not result.success and result.message in {
            "操作被策略阻止",
            "工具不存在",
            "操作被安全基线拦截",
        }:
            status = "denied"
        event.update(status=status)
        self._run_events.append(event)
        result.metadata["run_event"] = event.copy()
        logger.info(
            "executor.terminal request_id=%s task_id=%s run_id=%s status=%s step_id=%s category=%s",
            identity.request_id, identity.task_id, identity.run_id, status, event["step_id"],
            result.error_category,
        )
        return result

    # ------------------------------------------------------------------
    # 多步计划执行入口（P0 新增）
    # ------------------------------------------------------------------

    def execute_plan(
        self,
        steps,
        context: ExecutionContext,
        policy: ExecutionPolicy | None = None,
        plan_store=None,
        plan_id: str | None = None,
    ) -> PlanExecutionResult:
        """按顺序执行整个计划，带最大轮次、死循环检测与失败分级。

        失败分级策略：
        * fatal（参数/权限/未知错误）→ 立即终止整个计划并上报；
        * recoverable（业务错误/资源不存在）→ 记录结果继续后续步骤（换方案由上层重规划）；
        * retryable（网络/超时）→ 在单步内先走重试退避，重试耗尽按 recoverable 处理。

        传入 plan_store + plan_id 时，每步执行完立即落盘 checkpoint，
        中断后可用 `resume_plan` 从断点恢复（已成功步骤不重复执行）。
        """

        policy = policy or self.execution_policy
        context = deepcopy(context)
        identity = RunIdentity.create(request_id=context.request_id, task_id=context.task_id, run_id=context.run_id)
        fingerprints: deque[str] = deque(maxlen=policy.loop_window)
        plan_result = PlanExecutionResult(status="completed")

        for index, raw_step in enumerate(steps):
            if index >= policy.max_rounds:
                plan_result.status = "max_rounds_exceeded"
                plan_result.reason = f"达到最大轮次上限 {policy.max_rounds}，剩余 {len(steps) - index} 步未执行"
                break

            step = deepcopy(raw_step)
            step_result = self.execute(step, context)
            step_result.metadata["step_id"] = step.step_id
            plan_result.step_results.append(step_result)

            if plan_store is not None and plan_id:
                plan_store.record_step(
                    plan_id,
                    step.step_id,
                    success=step_result.success,
                    error_category=step_result.error_category,
                    error=step_result.error,
                )

            if step_result.success:
                continue

            # 死循环检测：同一 (工具, 参数) 指纹反复出现，说明在原地打转
            fingerprint = self._fingerprint(step)
            fingerprints.append(fingerprint)
            if fingerprints.count(fingerprint) >= policy.loop_threshold:
                plan_result.status = "aborted_loop"
                plan_result.reason = (
                    f"检测到死循环: 工具 {step.tool_name} 相同参数在最近 "
                    f"{policy.loop_window} 步内重复失败 {policy.loop_threshold} 次"
                )
                break

            failure_class = step_result.metadata.get("failure_class")
            if failure_class == "fatal":
                plan_result.status = "aborted_fatal"
                plan_result.reason = (
                    f"步骤 {step.step_id} ({step.tool_name}) 致命失败 "
                    f"[{step_result.error_category}]: {step_result.error}"
                )
                break

            # recoverable（含重试耗尽的可重试错误）：记录后继续
            logger.warning(
                "executor.step_recoverable request_id=%s step_id=%s tool=%s category=%s",
                identity.request_id, step.step_id, step.tool_name, step_result.error_category,
            )

        if plan_result.status == "completed" and plan_result.reason is None:
            plan_result.reason = f"全部 {len(plan_result.step_results)} 步执行完毕"

        if plan_store is not None and plan_id:
            plan_store.finish(plan_id, plan_result.status)

        return plan_result

    def resume_plan(
        self,
        plan_id: str,
        context: ExecutionContext,
        policy: ExecutionPolicy | None = None,
        plan_store=None,
    ) -> PlanExecutionResult:
        """断点续跑：加载持久化的计划状态，只执行尚未成功的步骤。

        服务重启 / 任务中断后调用；plan_store 未传入时要求构造时已配置。
        """

        store = plan_store or getattr(self, "_default_plan_store", None)
        if store is None:
            raise ValueError("resume_plan 需要 plan_store（或通过 with_plan_store 配置默认存储）")

        remaining = store.remaining_steps(plan_id)
        if not remaining:
            return PlanExecutionResult(
                status="completed",
                reason="所有步骤均已成功，无需续跑",
            )

        return self.execute_plan(
            remaining,
            context,
            policy=policy,
            plan_store=store,
            plan_id=plan_id,
        )

    def with_plan_store(self, plan_store):
        """配置默认计划存储，供 resume_plan 使用；返回自身支持链式调用。"""

        self._default_plan_store = plan_store
        return self

    @staticmethod
    def _fingerprint(step) -> str:
        try:
            arguments = json.dumps(step.arguments, sort_keys=True, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            arguments = str(step.arguments)
        return f"{step.tool_name}::{arguments}"

    # ------------------------------------------------------------------
    # 安全基线闸门辅助
    # ------------------------------------------------------------------

    # 只有承载可执行文本的参数键才送入命令红线匹配，
    # 普通业务参数（deviceKey、route 等）不参与，避免误报。
    _COMMAND_ARG_KEYS = ("command", "cmd", "script")

    def _extract_command_text(self, step) -> str:
        parts: list[str] = []
        for key in self._COMMAND_ARG_KEYS:
            value = (step.arguments or {}).get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        return "\n".join(parts)

    def _quota_scope_for(self, tool) -> str:
        risk = str(getattr(tool, "risk_level", "LOW")).upper()
        return "tool_high_risk" if risk in {"HIGH", "CRITICAL"} else "tool_default"

    def _run_baseline_gate(self, tool, step, context):
        command = self._extract_command_text(step)
        return self.security_engine.evaluate_operation(
            tool_name=step.tool_name,
            action=step.action,
            command=command,
            identity=context.user_id or "anonymous",
            quota_scope=self._quota_scope_for(tool),
            # dry-run 只做计划校验：红线照拦，但不消耗真实调用配额。
            consume_quota=not context.dry_run,
        )

    def _emit_baseline_event(self, decision, tool, step, context) -> None:
        engine = self.security_engine
        if engine is None:
            return
        reason = decision.reasons[0] if decision.reasons else ""
        if decision.layer is not None and decision.layer.value == "L0_COMPLIANCE":
            event_type = "baseline.compliance_hit"
        elif decision.layer is not None and decision.layer.value == "L2_OPERATIONS":
            event_type = "baseline.redline_hit"
        elif reason.startswith("QUOTA_EXHAUSTED"):
            event_type = "quota.exhausted"
        else:
            event_type = "baseline.blocked"
        engine.emit_event(
            event_type,
            layer=decision.layer or "",
            decision=decision.action.value,
            reasons=decision.reasons,
            evidence=decision.evidence,
            request_id=context.request_id,
            user_id=context.user_id,
            tool_name=step.tool_name,
            action=step.action,
        )

    # ------------------------------------------------------------------
    # 单步内部实现：校验 → 授权 → 超时/重试执行 → 截断
    # ------------------------------------------------------------------

    def _execute(
        self,
        step,
        context: ExecutionContext,
        run_event,
    ) -> ExecutionResult:

        # Execute the same snapshot that is checked and approved. The caller's
        # mutable plan/metadata must not change arguments during authorization.
        step = deepcopy(step)
        context = deepcopy(context)
        tool_name = step.tool_name

        tool = self.tool_registry.get(
            tool_name
        )

        if tool is None:
            return ExecutionResult(
                success=False,
                tool_name=tool_name,
                message="工具不存在",
                error=(
                    f"Tool not found: "
                    f"{tool_name}"
                ),
                error_category=ToolErrorCategory.RESOURCE_NOT_FOUND.value,
                metadata={"failure_class": "recoverable"},
            )

        # 安全基线硬闸门：L0 合规 → L2 红线 → L1 限流，先于人工审批链短路。
        # 挂载引擎时任何 BLOCK 都按 fatal 处理，下游步骤在 DAG 中自动 skip。
        if self.security_engine is not None:
            baseline_decision = self._run_baseline_gate(tool, step, context)
            if baseline_decision is not None and not baseline_decision.allowed:
                self._emit_baseline_event(baseline_decision, tool, step, context)
                result = ExecutionResult(
                    success=False,
                    tool_name=tool_name,
                    message="操作被安全基线拦截",
                    error="; ".join(baseline_decision.reasons) or "baseline blocked",
                    error_category=ToolErrorCategory.PERMISSION.value,
                    metadata={
                        "failure_class": "fatal",
                        "baseline_layer": (
                            baseline_decision.layer.value
                            if baseline_decision.layer else ""
                        ),
                        "baseline_reasons": list(baseline_decision.reasons),
                    },
                )
                self.audit_records.append(
                    AuditRecord.create(
                        run_event=run_event,
                        request_id=context.request_id,
                        user_id=context.user_id,
                        tool_name=tool_name,
                        action=step.action,
                        success=False,
                        risk_level=str(baseline_decision.risk),
                        error=result.error,
                    )
                )
                return result

        decision = self.policy_engine.authorize_execution(
            tool,
            context,
            step,
        )

        if not decision.allowed:
            if self.security_engine is not None and getattr(
                decision, "requires_approval", False
            ):
                # 高风险操作进入人工审批等待态——审批结论本身在 ApprovalManager 留痕，
                # 这里补一条基线审计事件，保证审批链路可从基线侧完整追溯。
                self.security_engine.emit_event(
                    "approval.requested",
                    layer="L2_OPERATIONS",
                    decision="APPROVAL_REQUIRED",
                    reasons=(decision.reason,),
                    request_id=context.request_id,
                    user_id=context.user_id,
                    tool_name=tool_name,
                    action=step.action,
                )
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                message="操作被策略阻止",
                error=decision.reason,
                error_category=ToolErrorCategory.PERMISSION.value,
                metadata={"failure_class": "fatal"},
            )

            self.audit_records.append(
                AuditRecord.create(
                    run_event=run_event,
                    request_id=context.request_id,
                    user_id=context.user_id,
                    tool_name=tool_name,
                    action=step.action,
                    success=False,
                    risk_level=tool.risk_level,
                    error=decision.reason,
                )
            )

            return result

        if self.security_engine is not None and context.approval_id:
            # 能走到这里说明审批指纹已校验并被 authorize_execution 消费。
            self.security_engine.emit_event(
                "approval.granted",
                layer="L2_OPERATIONS",
                decision="ALLOW",
                reasons=("approval_consumed",),
                request_id=context.request_id,
                user_id=context.user_id,
                tool_name=tool_name,
                action=step.action,
            )

        if context.dry_run:
            return ExecutionResult(
                success=True,
                tool_name=tool_name,
                message="Dry Run：未实际执行",
                output=step.arguments,
            )

        started = time.perf_counter()

        # OPS-01：实现状态不是 REAL 的工具在放行前就拒绝。
        # 否则模板命令会以"执行失败"的形态出现，把"没有实现"伪装成"跑了但出错"。
        definition = getattr(tool, "definition", None)
        status = getattr(definition, "implementation_status",
                         ImplementationStatus.REAL)
        if status != ImplementationStatus.REAL:
            return ExecutionResult(
                success=False,
                tool_name=tool_name,
                message="工具不可用",
                error=f"TOOL_IMPLEMENTATION_UNAVAILABLE: {tool_name} ({status})",
                duration_ms=0,
                error_category=ToolErrorCategory.RESOURCE_NOT_FOUND.value,
                metadata={"failure_class": "recoverable"},
            )

        # P0：参数 schema 校验，参数错误不进入真实执行，且不重试
        input_schema = getattr(definition, "input_schema", None) or {}
        try:
            validate_arguments(input_schema, step.arguments)
        except ToolExecutionError as exc:
            return self._build_failure_result(
                tool, step, run_event, context, exc, duration_ms=0,
                attempts=0,
            )

        # P0：超时 + 重试执行循环
        policy = self.execution_policy
        deadline_ms = int(getattr(definition, "deadline_ms", 0) or policy.default_step_timeout_ms)
        idempotency = getattr(definition, "idempotency", "SAFE_RETRY")

        max_attempts = 1 + max(0, policy.max_retries)
        attempts = 0
        result: ExecutionResult | None = None

        while attempts < max_attempts:
            attempts += 1
            try:
                output = self._invoke_with_timeout(tool, step.arguments, context, deadline_ms)
                reported = output if isinstance(output, dict) else (
                    {"success": output.success, "error": getattr(output, "error", None), "message": getattr(output, "message", None)}
                    if hasattr(output, "success") else {}
                )
                success = True
                error = None
                if "success" in reported:
                    if type(reported["success"]) is not bool:
                        exc = ToolExecutionError(
                            ToolErrorCategory.PARAMETER, "工具返回的 success 必须为布尔值",
                        )
                        raise exc
                    if reported["success"] is False:
                        success = False
                        error = str(reported.get("error") or reported.get("message") or "工具报告执行失败")

                duration_ms = int((time.perf_counter() - started) * 1000)
                output, truncated = truncate_output(
                    output, int(getattr(definition, "output_limit_bytes", 0) or 0),
                )

                result = ExecutionResult(
                    success=success,
                    tool_name=tool_name,
                    message="执行成功" if success else "执行失败",
                    output=output,
                    error=error,
                    duration_ms=duration_ms,
                    error_category=None if success else ToolErrorCategory.BUSINESS.value,
                    metadata={
                        "attempts": attempts,
                        "truncated": truncated,
                        "failure_class": None if success else FAILURE_GRADE[ToolErrorCategory.BUSINESS],
                        "timeout_ms": deadline_ms,
                    },
                )

                self.audit_records.append(
                    AuditRecord.create(
                        run_event=run_event,
                        request_id=context.request_id,
                        user_id=context.user_id,
                        tool_name=tool_name,
                        action=step.action,
                        success=success,
                        risk_level=tool.risk_level,
                        output=output,
                        error=error,
                    )
                )
                break

            except Exception as exc:
                classified = classify_exception(exc)
                result = self._build_failure_result(
                    tool, step, run_event, context, classified,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    attempts=attempts,
                    timeout_ms=deadline_ms,
                )
                can_retry = (
                    classified.retryable
                    and attempts < max_attempts
                    and idempotency == "SAFE_RETRY"
                )
                if not can_retry:
                    break
                backoff = policy.backoff_base_seconds * (2 ** (attempts - 1))
                logger.warning(
                    "executor.retry request_id=%s tool=%s attempt=%s category=%s backoff=%.2fs",
                    context.request_id, tool_name, attempts, classified.category.value, backoff,
                )
                policy.sleep_fn(backoff)

        assert result is not None
        return result

    def _invoke_with_timeout(self, tool, arguments, context, deadline_ms):
        """在独立线程执行工具调用并强制超时，防止单个工具卡死整个执行循环。"""

        timeout_seconds = max(deadline_ms, 1) / 1000.0
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._invoke, tool, arguments, context)
            try:
                return future.result(timeout=timeout_seconds)
            except FutureTimeoutError:
                future.cancel()
                raise ToolExecutionError(
                    ToolErrorCategory.TIMEOUT,
                    f"工具执行超过 {deadline_ms}ms 预算被终止",
                ) from None

    def _build_failure_result(
        self,
        tool,
        step,
        run_event,
        context: ExecutionContext,
        exc: ToolExecutionError,
        duration_ms: int,
        attempts: int,
        timeout_ms: int | None = None,
    ) -> ExecutionResult:
        metadata: dict[str, Any] = {
            "attempts": attempts,
            "failure_class": FAILURE_GRADE[exc.category],
        }
        if timeout_ms is not None:
            metadata["timeout_ms"] = timeout_ms

        result = ExecutionResult(
            success=False,
            tool_name=step.tool_name,
            message="执行失败",
            error=str(exc),
            duration_ms=duration_ms,
            error_category=exc.category.value,
            metadata=metadata,
        )

        self.audit_records.append(
            AuditRecord.create(
                run_event=run_event,
                request_id=context.request_id,
                user_id=context.user_id,
                tool_name=step.tool_name,
                action=step.action,
                success=False,
                risk_level=tool.risk_level,
                error=str(exc),
            )
        )
        return result

    def get_audit_records(self):
        return list(
            self.audit_records
        )

    def _invoke(self, tool, arguments, context):
        """统一工具调用契约（OPS-01）。

        * 插件工具：`async execute(arguments, context)`
        * 旧式内置工具：同步 `execute(**arguments)`

        两种契约都走同一个入口，避免"注册的是异步插件、调用的是同步可调用"的错配。
        """
        execute = getattr(tool, "execute")
        if inspect.iscoroutinefunction(execute):
            return self._run_coroutine(execute(arguments, context))
        return execute(**arguments)

    @staticmethod
    def _run_coroutine(coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # 常见路径：同步上下文，直接跑完事件循环
            return asyncio.run(coroutine)
        # 已有事件循环时不能嵌套 asyncio.run，放到独立线程执行，
        # 保持 Executor 的同步返回契约，也避免把调用方的事件循环阻塞死。
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coroutine).result()

    def get_run_events(self):
        return deepcopy(self._run_events)
