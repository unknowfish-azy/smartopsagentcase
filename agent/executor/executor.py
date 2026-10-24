import time

from .audit import AuditRecord
from .models import ExecutionContext
from .result import ExecutionResult


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

    def execute(
        self,
        step,
        context: ExecutionContext,
    ) -> ExecutionResult:

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

        decision = self.policy_engine.check(
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

            duration_ms = int(
                (
                    time.perf_counter()
                    - started
                )
                * 1000
            )

            result = ExecutionResult(
                success=True,
                tool_name=tool_name,
                message="执行成功",
                output=output,
                duration_ms=duration_ms,
            )

            self.audit_records.append(
                AuditRecord.create(
                    request_id=context.request_id,
                    user_id=context.user_id,
                    tool_name=tool_name,
                    action=step.action,
                    success=True,
                    risk_level=tool.risk_level,
                    output=output,
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