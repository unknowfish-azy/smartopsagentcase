import logging
import time
from copy import deepcopy
from agent.runtime_events import RunIdentity, terminal_event

from .audit import AuditRecord
from .models import ExecutionContext
from .result import ExecutionResult


logger = logging.getLogger(__name__)


class AgentExecutor:
    """
    Agent 工具执行器。

    Executor 不负责决定执行什么。
    执行计划由 Planner 负责生成，
    是否允许执行由 Policy Engine 决定。
    """

    def __init__(
        self,
        tool_registry,
        policy_engine,
    ):
        self.tool_registry = tool_registry
        self.policy_engine = policy_engine
        self.audit_records: list[
            AuditRecord
        ] = []
        self._run_events = []

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
        if not result.success and result.message in {"操作被策略阻止", "工具不存在"}:
            status = "denied"
        event.update(status=status)
        self._run_events.append(event)
        result.metadata["run_event"] = event.copy()
        logger.info(
            "executor.terminal request_id=%s task_id=%s run_id=%s status=%s step_id=%s",
            identity.request_id, identity.task_id, identity.run_id, status, event["step_id"],
        )
        return result

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
            )

        decision = self.policy_engine.authorize_execution(
            tool,
            context,
            step,
        )

        if not decision.allowed:
            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                message="操作被策略阻止",
                error=decision.reason,
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

        if context.dry_run:
            return ExecutionResult(
                success=True,
                tool_name=tool_name,
                message="Dry Run：未实际执行",
                output=step.arguments,
            )

        started = time.perf_counter()

        try:
            output = tool.execute(
                **step.arguments
            )

            success = True
            error = None
            reported = output if isinstance(output, dict) else (
                {"success": output.success, "error": getattr(output, "error", None), "message": getattr(output, "message", None)}
                if hasattr(output, "success") else {}
            )
            if "success" in reported:
                if type(reported["success"]) is not bool:
                    success, error = False, "工具返回的 success 必须为布尔值"
                elif reported["success"] is False:
                    success = False
                    error = str(reported.get("error") or reported.get("message") or "工具报告执行失败")

            duration_ms = int(
                (
                    time.perf_counter()
                    - started
                )
                * 1000
            )

            result = ExecutionResult(
                success=success,
                tool_name=tool_name,
                message="执行成功" if success else "执行失败",
                output=output,
                error=error,
                duration_ms=duration_ms,
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

            return result

        except Exception as exc:

            duration_ms = int(
                (
                    time.perf_counter()
                    - started
                )
                * 1000
            )

            result = ExecutionResult(
                success=False,
                tool_name=tool_name,
                message="执行失败",
                error=str(exc),
                duration_ms=duration_ms,
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
                    error=str(exc),
                )
            )

            return result

    def get_audit_records(self):
        return list(
            self.audit_records
        )

    def get_run_events(self):
        return deepcopy(self._run_events)
