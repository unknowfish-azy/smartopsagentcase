"""统一 Agent Runtime：所有执行入口的唯一装配点。

在此之前，带安全基线的执行器只被 CLI 和测试使用，线上聊天走 RAG、
ReAct 规划器又没挂基线，形成"安全能力存在但线上不生效"的断点。
本模块把「输入闸门 → 计划/ReAct 执行 → 输出审核」收敛到一处：

* chat 纯问答仍走 ChatService；
* 需要执行/巡检/处置时转到这里，执行链固定挂 L0-L3 基线；
* 输入侧命中注入直接 BLOCK（fail-closed），并写审计事件；
* 输出侧再过一遍脱敏与越权承诺改写。

依赖方向单向：ai-service → agent，agent 不反向依赖本模块。
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agent.assembly import AgentAssembly, build_agent_assembly  # noqa: E402
from agent.awareness import SecurityBriefBuilder  # noqa: E402
from agent.executor.models import ExecutionContext  # noqa: E402
from agent.inspector.judges.rule_judge import is_state_changing  # noqa: E402
from agent.inspector.models import EvidenceItem, ToolCallRecord  # noqa: E402
from agent.inspector.service import InspectorService  # noqa: E402
from agent.inspector.verifiers.state_verifier import collect_probes  # noqa: E402
from agent.planner.react_agent import build_react_planner  # noqa: E402
from agent.planner.steps import PlanStep  # noqa: E402
from agent.security_baseline import (  # noqa: E402
    DEFAULT_AUDIT_DIR,
    GateAction,
    SecurityBaselineBundle,
    build_security_baseline,
)

logger = logging.getLogger(__name__)


class _AuditEmitterRef:
    """可深拷贝的审计发射器引用。

    Executor 会 deepcopy ExecutionContext，而基线引擎的 bound method 持有
    RLock 无法 pickle；这里用引用包装让 deepcopy 原样返回，同时保持可调用。
    """

    __slots__ = ("_emitter",)

    def __init__(self, emitter) -> None:
        self._emitter = emitter

    def __call__(self, *args, **kwargs):
        return self._emitter(*args, **kwargs)

    def __deepcopy__(self, memo):
        return self


def _baseline_enabled_by_config() -> bool:
    """读取部署配置；读不到配置时按安全优先默认开启。"""
    try:
        from ..core.config import settings

        return bool(settings.security_baseline_enabled)
    except Exception:  # noqa: BLE001 - 独立运行时没有 ai-service 配置
        logger.debug("agent_runtime.settings_unavailable", exc_info=True)
        return True


@dataclass
class AgentRunResult:
    """一次 Agent 运行的结构化结果（入口层直接序列化返回）。"""

    status: str
    request_id: str
    user_id: str
    run_id: str
    risk: str = "LOW"
    answer: str = ""
    reason: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    page_context: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False
    verification_status: str = "not_required"
    verification: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    # W2：确定性安全简报（smartops.security_brief.v1）。
    brief: dict[str, Any] | None = None
    # W6：Trust Ledger 回放所需的工具时间线（真实执行结果，不含原始输出）。
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    approval_id: str | None = None

    def __post_init__(self) -> None:
        # closure 等既有下游从 metadata 读取核验结论，避免仅凭执行成功写回 resolved。
        self.metadata.setdefault("verification_status", self.verification_status)
        if self.verification:
            self.metadata.setdefault("verification", self.verification)

    @property
    def execution_status(self) -> str:
        """执行状态与目标核验状态分离；保留 status 兼容既有调用方。"""
        return self.status

    @property
    def verified(self) -> bool:
        return self.verification_status == "verified"

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "execution_status": self.execution_status,
            "verification_status": self.verification_status,
            "verified": self.verified,
            "verification": self.verification,
            "request_id": self.request_id,
            "user_id": self.user_id,
            "run_id": self.run_id,
            "risk": self.risk,
            "answer": self.answer,
            "reason": self.reason,
            "steps": self.steps,
            "page_context": self.page_context,
            "dry_run": self.dry_run,
            "metadata": self.metadata,
            "brief": self.brief,
            "tool_calls": self.tool_calls,
            "approval_id": self.approval_id,
        }


class AgentRuntime:
    """统一 Agent 执行入口。"""

    def __init__(
        self,
        *,
        bundle: SecurityBaselineBundle | None = None,
        tools: Iterable[Any] = (),
        model_provider=None,
        inspector: InspectorService | None = None,
        security_enabled: bool | None = None,
        audit_dir: str | Path | None = None,
    ) -> None:
        # None = 跟随部署配置；显式 True/False 用于测试与调用方强制语义。
        if security_enabled is None:
            security_enabled = _baseline_enabled_by_config()
        self.security_enabled = security_enabled
        self.bundle = (
            self._resolve_bundle(audit_dir) if security_enabled and bundle is None else bundle
        )
        if security_enabled and self.bundle is None:
            # 基线开启但装配不出 bundle：按 fail-closed 拒绝启动执行链。
            raise RuntimeError("安全基线已开启但无法装配 bundle，拒绝裸奔执行")
        self.assembly: AgentAssembly = build_agent_assembly(
            tools=tools,
            security_enabled=security_enabled,
            bundle=self.bundle,
        )
        self.model_provider = model_provider
        self.brief_builder = SecurityBriefBuilder()
        self.inspector = inspector or InspectorService()

    # ------------------------------------------------------------------
    # 运行入口
    # ------------------------------------------------------------------

    def run(
        self,
        *,
        goal: str,
        user_id: str = "anonymous",
        request_id: str | None = None,
        steps: list[dict[str, Any]] | None = None,
        dry_run: bool = False,
        approval_id: str | None = None,
        page_context: dict[str, Any] | None = None,
        max_iterations: int = 6,
        actual_state: dict[str, Any] | None = None,
        verification_targets: Any = None,
        forwarded_headers: dict[str, str] | None = None,
    ) -> AgentRunResult:
        request_id = request_id or uuid.uuid4().hex
        page_context = page_context or {}
        engine = self.bundle.engine if self.bundle else None
        risk = "LOW"

        # W2：简报先于执行生成——"先说风险，再动手"。
        step_tools = [
            str(item.get("tool_name", ""))
            for item in (steps or [])
            if item.get("tool_name")
        ]
        base_sources = ["BASELINE"] if engine is not None else []

        def _make_brief(
            *,
            run_id: str | None = None,
            risk_floor=None,
            extra_reasons=(),
            evidence_refs=(),
            sources: list[str] | None = None,
            tool_names: list[str] | None = None,
        ) -> dict[str, Any]:
            return self.brief_builder.build(
                message=goal,
                run_id=run_id or request_id,
                tool_names=tool_names if tool_names is not None else step_tools,
                page_context=page_context,
                evidence_refs=evidence_refs,
                data_sources=sources if sources is not None else base_sources,
                approval_id=approval_id,
                risk_floor=risk_floor,
                extra_reasons=extra_reasons,
            ).to_dict()

        brief = _make_brief()

        # 1) 输入闸门：注入/合规命中即短路，不进入规划与执行。
        text = goal
        if engine is not None:
            decision = engine.evaluate_input(goal)
            risk = decision.risk.value
            if not decision.allowed:
                engine.emit_event(
                    "baseline.blocked",
                    layer=decision.layer or "",
                    decision="BLOCK",
                    reasons=decision.reasons,
                    request_id=request_id,
                    user_id=user_id,
                    extra={"entry": "agent_runtime", "stage": "input"},
                )
                return AgentRunResult(
                    status="blocked",
                    request_id=request_id,
                    user_id=user_id,
                    run_id=request_id,
                    risk=risk,
                    reason="; ".join(decision.reasons),
                    answer="该请求被安全基线拦截，未执行任何工具。",
                    page_context=page_context,
                    dry_run=dry_run,
                    brief=_make_brief(risk_floor=risk, extra_reasons=decision.reasons),
                )
            if decision.action is GateAction.REDACT and decision.redacted_text:
                text = decision.redacted_text

        context = ExecutionContext(
            request_id=request_id,
            user_id=user_id,
            dry_run=dry_run,
            approval_id=approval_id,
            metadata={
                "page_context": page_context,
                "entry": "agent_runtime",
                # 写工具要求"审计必发"：基线开启时把 emit_event 注入上下文。
                "audit_emitter": _AuditEmitterRef(engine.emit_event) if engine is not None else None,
                # 当前用户会话头（Cookie/CSRF 等）透传给产品接口，避免超级账号越权。
                "forwarded_headers": dict(forwarded_headers or {}),
            },
        )

        # 2) 执行与核验分离：工具成功只代表调用结束，不代表目标已经恢复。
        plan_steps = []
        execution_results = []
        react_result = None
        try:
            if steps:
                plan_steps = [PlanStep.from_dict(item) for item in steps]
                plan_result = self.assembly.executor.execute_plan(plan_steps, context)
                execution_results = plan_result.step_results
                status = plan_result.status
                answer = self._summarize(plan_result)
                step_dicts = plan_result.to_dict().get("steps", [])
                reason = plan_result.reason or ""
            else:
                planner = build_react_planner(
                    provider=self.model_provider,
                    tool_registry=self.assembly.tool_registry,
                    executor=self.assembly.executor,
                    max_iterations=max_iterations,
                    security_enabled=False,
                )
                react_result = planner.run(text, context)
                status = react_result.status
                answer = react_result.final_answer
                reason = ""
                step_dicts = []

            verification = self._verify_execution(
                task_id=context.run_id,
                answer=answer,
                plan_steps=plan_steps,
                execution_results=execution_results,
                trajectory=react_result.trajectory if react_result is not None else [],
                context=context,
                actual_state=actual_state,
                verification_targets=verification_targets,
            )
            verification_status = verification["verification_result"]["status"]
            if react_result is not None:
                react_result.metadata["verification_status"] = verification_status
                react_result.metadata["verification"] = verification
        except Exception as exc:  # noqa: BLE001 - 入口统一转结构化失败，细节进日志
            logger.exception("agent_runtime.execution_failed request_id=%s", request_id)
            return AgentRunResult(
                status="error",
                request_id=request_id,
                user_id=user_id,
                run_id=context.run_id,
                risk=risk,
                reason=f"{type(exc).__name__}: {exc}",
                answer="",
                page_context=page_context,
                dry_run=dry_run,
                verification_status="unverified",
                brief=brief,
                tool_calls=[],  # 执行在抛出前未形成可回放轨迹，不补造。
                approval_id=approval_id,
            )

        # W6：把真实执行轨迹折算成 Trust Ledger 可回放的工具时间线（不含工具原始输出）。
        if execution_results:
            tool_calls = self._plan_tool_calls(plan_steps, execution_results)
        elif react_result is not None:
            tool_calls = self._react_tool_calls(react_result.trajectory)
        else:
            tool_calls = []

        # 3) 输出闸门：脱敏与越权承诺改写，BLOCK 时不给结论。
        if engine is not None and answer:
            review = engine.review_output(answer)
            if not review.allowed:
                return AgentRunResult(
                    status="blocked_output",
                    request_id=request_id,
                    user_id=user_id,
                    run_id=context.run_id,
                    risk=risk,
                    reason="; ".join(review.reasons),
                    answer="输出未通过安全审核，已拦截。",
                    page_context=page_context,
                    dry_run=dry_run,
                    verification_status=verification_status,
                    verification=verification,
                    brief=brief,
                    tool_calls=tool_calls,
                    approval_id=approval_id,
                )
            if review.action is GateAction.REDACT and review.redacted_text:
                answer = review.redacted_text

        executed_tools = list(step_tools)
        if react_result is not None:
            executed_tools += [
                str(getattr(step, "action", ""))
                for step in react_result.trajectory
                if getattr(step, "success", False) and getattr(step, "action", "")
            ]
        executed_tools = list(dict.fromkeys(executed_tools))
        brief = _make_brief(
            run_id=context.run_id,
            evidence_refs=[f"run:{context.run_id}"] + [f"tool:{name}" for name in executed_tools],
            sources=base_sources + (["TOOL"] if executed_tools else []),
            tool_names=executed_tools,
        )

        return AgentRunResult(
            status=status,
            request_id=request_id,
            user_id=user_id,
            run_id=context.run_id,
            risk=risk,
            answer=answer,
            reason=reason,
            steps=step_dicts,
            page_context=page_context,
            dry_run=dry_run,
            verification_status=verification_status,
            verification=verification,
            brief=brief,
            tool_calls=tool_calls,
            approval_id=approval_id,
        )

    # ------------------------------------------------------------------
    # Trust Ledger 工具时间线
    # ------------------------------------------------------------------

    def _risk_of(self, tool_name: str) -> str:
        """读取工具声明的风险等级；读不到时返回空串（不臆造）。"""
        try:
            tool = self.assembly.tool_registry.get(tool_name)
            definition = getattr(tool, "definition", None)
            raw = getattr(definition, "risk", getattr(tool, "risk_level", ""))
            return str(getattr(raw, "value", raw) or "").upper()
        except Exception:  # noqa: BLE001 - 未注册工具不影响结果返回
            return ""

    def _plan_tool_calls(self, plan_steps, execution_results) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index, result in enumerate(execution_results):
            step = plan_steps[index] if index < len(plan_steps) else None
            tool_name = getattr(result, "tool_name", "") or ""
            rows.append(
                {
                    "stepId": getattr(step, "step_id", index + 1),
                    "toolName": tool_name,
                    "action": str(getattr(step, "action", "") or ""),
                    "risk": self._risk_of(tool_name),
                    "success": bool(getattr(result, "success", False)),
                    "errorCategory": getattr(result, "error_category", None),
                    "attempts": (getattr(result, "metadata", {}) or {}).get("attempts"),
                    "requiresApproval": bool(getattr(step, "requires_approval", False)),
                }
            )
        return rows

    def _react_tool_calls(self, trajectory) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for step in trajectory or []:
            tool_name = str(getattr(step, "action", "") or "")
            if not tool_name:
                continue
            rows.append(
                {
                    "stepId": getattr(step, "iteration", len(rows) + 1),
                    "toolName": tool_name,
                    "action": tool_name,
                    "risk": self._risk_of(tool_name),
                    "success": bool(getattr(step, "success", False)),
                    "errorCategory": None,
                    "attempts": None,
                    "requiresApproval": False,
                    "duplicate": bool(getattr(step, "duplicate", False)),
                }
            )
        return rows

    def _verify_execution(
        self,
        *,
        task_id: str,
        answer: str,
        plan_steps: list[PlanStep],
        execution_results: list[Any],
        trajectory: list[Any],
        context: ExecutionContext,
        actual_state: dict[str, Any] | None,
        verification_targets: Any,
    ) -> dict[str, Any]:
        """复用 Inspector 核验最终结论，不把工具 success 当作目标成功。"""
        if context.dry_run:
            # Dry Run 没有真实后置状态，即使计划包含变更工具也不要求探针核验。
            return self.inspector.inspect(
                task_id=task_id,
                agent_claim=None,
                metadata={"dry_run": True, "entry": "agent_runtime"},
            ).to_dict()

        # 显式 actual_state 优先；否则可由调用方给出目标，复用现有有界只读探针采集。
        observed_state = actual_state
        if observed_state is None and verification_targets is not None:
            observed_state = {"probes": collect_probes(verification_targets)}

        evidence: list[EvidenceItem] = []
        tool_calls: list[ToolCallRecord] = []
        verification_required = False

        def successful_call(tool_name: str, arguments: dict[str, Any]):
            tool = self.assembly.tool_registry.get(tool_name)
            definition = getattr(tool, "definition", None)
            risk = getattr(definition, "risk", getattr(tool, "risk_level", "LOW"))
            risk_value = str(getattr(risk, "value", risk)).upper()
            required = (
                bool(str(getattr(definition, "verification", "") or "").strip())
                or str(getattr(definition, "idempotency", "SAFE_RETRY")).upper() != "SAFE_RETRY"
                or is_state_changing(tool_name)
            )
            return ToolCallRecord(
                tool_name=tool_name,
                risk=risk_value,
                approval_granted=bool(context.approval_id),
                success=True,
                args=dict(arguments or {}),
            ), required

        for index, result in enumerate(execution_results):
            arguments = plan_steps[index].arguments if index < len(plan_steps) else {}
            content = (
                result.output
                if result.success and result.output is not None
                else result.error or result.message
            )
            if content not in (None, ""):
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False, default=str)
                evidence.append(EvidenceItem(content=content, source=result.tool_name))
            # 被拒绝、待审批或失败的调用不算已经成功执行，避免核验器误判审批绕过。
            if not result.success:
                continue
            call, required = successful_call(result.tool_name, arguments)
            tool_calls.append(call)
            verification_required = verification_required or required

        for step in trajectory:
            if not getattr(step, "action", "") or getattr(step, "duplicate", False):
                continue
            if getattr(step, "success", None) is None:
                continue
            content = getattr(step, "observation", "")
            if content:
                evidence.append(EvidenceItem(content=str(content), source=step.action))
            if not step.success:
                continue
            call, required = successful_call(step.action, step.action_input)
            tool_calls.append(call)
            verification_required = verification_required or required

        inspection = self.inspector.inspect(
            task_id=task_id,
            agent_claim=answer,
            evidence=evidence,
            tool_calls=tool_calls,
            actual_state=observed_state,
            metadata={
                "entry": "agent_runtime",
                "verification_required": verification_required,
            },
        )
        return inspection.to_dict()

    # ------------------------------------------------------------------
    # 内部装配
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_bundle(audit_dir: str | Path | None) -> SecurityBaselineBundle | None:
        """优先复用 ai-service lifespan 装配的单例，避免多份 sink 并写同一条链。"""
        try:
            from ..core.baseline import get_bundle

            existing = get_bundle()
            if existing is not None:
                return existing
        except Exception:  # noqa: BLE001 - 未启动 lifespan 时走本地装配
            logger.debug("agent_runtime.bundle_singleton_unavailable", exc_info=True)

        try:
            from ..core.config import settings

            target = Path(settings.security_audit_dir)
            if not target.is_absolute():
                target = _REPO_ROOT / target
            config_path = settings.security_baseline_config_path or None
            if config_path and not Path(config_path).is_absolute():
                config_path = str(_REPO_ROOT / config_path)
        except Exception:  # noqa: BLE001 - 无 settings 时退回默认目录
            target, config_path = audit_dir or DEFAULT_AUDIT_DIR, None

        return build_security_baseline(audit_dir=target, config_path=config_path)

    @staticmethod
    def _summarize(plan_result) -> str:
        total = len(plan_result.step_results)
        ok = sum(1 for item in plan_result.step_results if item.success)
        return f"计划执行结束：{plan_result.status}，成功 {ok}/{total} 步。{plan_result.reason or ''}".strip()


__all__ = ["AgentRunResult", "AgentRuntime"]
