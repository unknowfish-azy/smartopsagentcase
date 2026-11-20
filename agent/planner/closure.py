"""M1-4 / M1-5 / M1-6 处置闭环收尾。

ReAct 循环负责「取证 → 研判」，真正把一次故障处置变成可复用经验还需要收尾：

* **M1-4 执行结果归档**：把轨迹里的工具执行结果折算成 ExecutionResult 视图，
  交给既有 Reflector 评审（复用 agent/reflection，不改其语义）；
* **M1-5 记忆写回**：处置记录写入 LongTermMemory（按 user 隔离、带 TTL），
  下次同类故障可直接检索；
* **M1-6 反思反哺**：通过已注册的 `nn.learn_from_incident` 写回案例库，
  让下一次 `nn.retrieve` 能召回本次经验。写回失败只记录，不中断收尾。

设计边界：本模块只做串联与归档，不新增决策；风险分级 / 审批 / 回滚仍由
执行器与 risk / approval 模块负责（M1-4 复用现状）。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agent.executor.executor import AgentExecutor
from agent.executor.models import ExecutionContext
from agent.executor.result import ExecutionResult
from agent.memory.long_term import LongTermMemory
from agent.memory.models import MemoryItem
from agent.planner.evidence import EVIDENCE_TOOL_NAMES, EvidenceBundle
from agent.planner.steps import PlanStep
from agent.reflection.reflection import Reflector, ReflectionVerdict

logger = logging.getLogger(__name__)

# 与 ai-service 的 category 枚举保持一致
_VALID_CATEGORIES = (
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error", "other",
)
_VALID_OUTCOMES = ("resolved", "mitigated", "failed", "pending")

WRITEBACK_TOOL = "nn.learn_from_incident"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class IncidentRecord:
    """一次故障处置的归档记录（本地记忆 + 案例库共用同一份事实）。"""

    incident_key: str
    goal: str
    status: str
    outcome: str
    category: str = "other"
    severity: str = "P2"
    symptom: str = ""
    analysis: str = ""
    action_taken: str = "wait_and_observe"
    root_cause: str = ""
    duration_minutes: int | None = None
    lesson: str | None = None
    reflection: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "incident_key": self.incident_key,
            "goal": self.goal,
            "status": self.status,
            "outcome": self.outcome,
            "category": self.category,
            "severity": self.severity,
            "symptom": self.symptom,
            "analysis": self.analysis,
            "action_taken": self.action_taken,
            "root_cause": self.root_cause,
            "duration_minutes": self.duration_minutes,
            "lesson": self.lesson,
            "reflection": self.reflection,
            "evidence": self.evidence,
            "metrics": self.metrics,
            "created_at": self.created_at,
        }

    def to_writeback_payload(self) -> dict[str, Any]:
        """转成 nn.learn_from_incident 的入参（字段与 ai-service schema 对齐）。"""

        payload: dict[str, Any] = {
            "incident_key": self.incident_key,
            "category": self.category,
            "severity": self.severity,
            "symptom": self.symptom or self.goal,
            "analysis": self.analysis,
            "action_taken": self.action_taken,
            "outcome": self.outcome,
        }
        if self.duration_minutes is not None:
            payload["duration_minutes"] = self.duration_minutes
        if self.lesson:
            payload["lesson"] = self.lesson
        return payload


class _PlanView:
    """Reflector 需要的 plan_result 最小视图。"""

    def __init__(self, status: str, step_results: list[ExecutionResult]) -> None:
        self.status = status
        self.step_results = step_results


class IncidentClosure:
    """把 ReAct 结果收尾成「反思 + 记忆 + 案例库写回」。"""

    def __init__(
        self,
        memory: LongTermMemory,
        *,
        reflector: Reflector | None = None,
        executor: AgentExecutor | None = None,
        tool_registry: Any = None,
        writeback_tool: str = WRITEBACK_TOOL,
        memory_ttl_seconds: int | None = 30 * 24 * 3600,
        enable_writeback: bool = True,
    ) -> None:
        self.memory = memory
        self.reflector = reflector or Reflector()
        self.executor = executor
        self.tool_registry = tool_registry
        self.writeback_tool = writeback_tool
        self.memory_ttl_seconds = memory_ttl_seconds
        self.enable_writeback = enable_writeback

    # ------------------------------------------------------------------
    # 对外入口
    # ------------------------------------------------------------------

    def close(
        self,
        goal: str,
        result,
        context: ExecutionContext,
        *,
        outcome: str | None = None,
        success: bool | None = None,
        category: str | None = None,
        severity: str = "P2",
        action_taken: str | None = None,
        duration_minutes: int | None = None,
        lesson: str | None = None,
        incident_key: str | None = None,
    ) -> IncidentRecord:
        """收尾一次 ReAct 执行；任何写回失败都不抛出，只记录状态。

        outcome 判定优先级：
          1) 显式 outcome（调用方直接给完整枚举）
          2) 显式 success（布尔 → 枚举）：True 先按 resolved 候选；False 视 status 降级
          3) 都没传 → 自动推断（status + Reflector verdict）

        所有 resolved 候选最终都必须有 metadata.verification_status == "verified"；
        显式 success=False 时绝不会被判为 resolved，避免失败经验污染记忆库。
        """

        key = incident_key or f"inc-{uuid.uuid4().hex[:12]}"
        verdict = self._review(goal, result)
        resolved_outcome = self._resolve_outcome(outcome, success, result, verdict)
        if resolved_outcome not in _VALID_OUTCOMES:
            resolved_outcome = "pending"
        # 最终防绕过：无论 outcome 是自动推断还是调用方显式指定，
        # 没有真实后置状态核验通过，都不得把经验写成 resolved。
        if resolved_outcome == "resolved" and not self._verification_passed(result):
            resolved_outcome = (
                "mitigated" if getattr(result, "status", "") == "completed" else "pending"
            )

        derived_category = category or self._infer_category(result)
        if derived_category not in _VALID_CATEGORIES:
            derived_category = "other"

        record = IncidentRecord(
            incident_key=key,
            goal=goal,
            status=str(getattr(result, "status", "")),
            outcome=resolved_outcome,
            category=derived_category,
            severity=severity,
            symptom=goal,
            analysis=str(getattr(result, "final_answer", "") or ""),
            action_taken=action_taken or self._infer_action(result),
            root_cause=self._infer_root_cause(result),
            duration_minutes=duration_minutes,
            lesson=lesson,
            reflection={
                "decision": verdict.decision,
                "reason": verdict.reason,
                "source": verdict.source,
                "failed_step_ids": list(verdict.failed_step_ids),
            },
            evidence=self._evidence_dict(result),
            metrics=dict((getattr(result, "metadata", {}) or {}).get("stats") or {}),
        )

        self._save_memory(record, context)
        if self.enable_writeback:
            record.metrics["writeback"] = self._writeback(record, context)
        return record

    # ------------------------------------------------------------------
    # 反思
    # ------------------------------------------------------------------

    def _review(self, goal: str, result) -> ReflectionVerdict:
        try:
            return self.reflector.review(goal, _PlanView(result.status, self._step_results(result)))
        except Exception as exc:  # noqa: BLE001 - 收尾阶段不允许因反思失败中断
            logger.warning("incident closure reflect failed: %s", exc)
            return ReflectionVerdict(decision="pass" if getattr(result, "success", False) else "replan",
                                     reason=f"反思失败已降级：{type(exc).__name__}")

    @staticmethod
    def _step_results(result) -> list[ExecutionResult]:
        """把 ReAct 轨迹折算成 ExecutionResult，供 Reflector 复用。"""

        step_results: list[ExecutionResult] = []
        for index, step in enumerate(getattr(result, "trajectory", []) or [], start=1):
            if not getattr(step, "action", "") or getattr(step, "duplicate", False):
                continue
            success = bool(step.success)
            observation = str(getattr(step, "observation", "") or "")
            step_results.append(
                ExecutionResult(
                    success=success,
                    tool_name=step.action,
                    message=observation,
                    output=None,
                    error=None if success else observation,
                    metadata={"step_id": index},
                )
            )
        return step_results

    # ------------------------------------------------------------------
    # outcome 判定（显式入参优先，禁止失败经验被误标 resolved）
    # ------------------------------------------------------------------

    def _resolve_outcome(
        self,
        outcome: str | None,
        success: bool | None,
        result,
        verdict: ReflectionVerdict,
    ) -> str:
        if outcome is not None:
            return outcome
        if success is not None:
            if success:
                return "resolved"
            # 显式失败：按 ReAct 收尾状态降级，绝不再判 resolved
            status = getattr(result, "status", "")
            if status == "completed":
                return "mitigated"
            if status in {"needs_approval", "max_iterations"}:
                return "pending"
            return "failed"
        return self._infer_outcome(result, verdict)

    @staticmethod
    def _verification_passed(result) -> bool:
        metadata = getattr(result, "metadata", {}) or {}
        return metadata.get("verification_status") == "verified"

    @staticmethod
    def _infer_outcome(result, verdict: ReflectionVerdict) -> str:
        if getattr(result, "status", "") == "completed" and verdict.decision == "pass":
            return "resolved"
        if getattr(result, "status", "") == "completed":
            return "mitigated"
        if getattr(result, "status", "") in {"needs_approval", "max_iterations"}:
            return "pending"
        return "failed"

    # ------------------------------------------------------------------
    # 事实抽取
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_category(result) -> str:
        bundle = getattr(result, "evidence", None)
        if not isinstance(bundle, EvidenceBundle):
            return "other"
        log_item = bundle.items.get("nn.log_classify")
        if log_item is not None:
            distribution = {
                str(entry.get("label")): entry.get("count")
                for entry in log_item.top_k
                if entry.get("label") in _VALID_CATEGORIES
            }
            if distribution:
                return max(distribution, key=lambda label: distribution[label] or 0)
        case_item = bundle.items.get("nn.retrieve")
        if case_item is not None and case_item.top_k:
            top_category = case_item.top_k[0].get("category")
            if top_category in _VALID_CATEGORIES:
                return str(top_category)
        return "other"

    @staticmethod
    def _infer_action(result) -> str:
        for step in reversed(getattr(result, "trajectory", []) or []):
            action = getattr(step, "action", "")
            if action and action not in EVIDENCE_TOOL_NAMES:
                return str(action)
        return "wait_and_observe"

    @staticmethod
    def _infer_root_cause(result) -> str:
        bundle = getattr(result, "evidence", None)
        if isinstance(bundle, EvidenceBundle):
            item = bundle.items.get("nn.rootcause")
            if item is not None and item.top_k:
                alert_id = item.top_k[0].get("alert_id")
                if alert_id is not None:
                    return str(alert_id)
        return ""

    @staticmethod
    def _evidence_dict(result) -> dict[str, Any]:
        bundle = getattr(result, "evidence", None)
        if isinstance(bundle, EvidenceBundle):
            return bundle.to_dict()
        return {"items": {}, "missing": list(EVIDENCE_TOOL_NAMES)}

    # ------------------------------------------------------------------
    # 写回
    # ------------------------------------------------------------------

    def _save_memory(self, record: IncidentRecord, context: ExecutionContext) -> None:
        self.memory.save(
            MemoryItem(
                key=f"incident:{record.incident_key}",
                value=record.to_dict(),
                memory_type="incident",
                owner=getattr(context, "user_id", None),
                ttl_seconds=self.memory_ttl_seconds,
                tags=[record.category, record.outcome],
            )
        )

    def _writeback(self, record: IncidentRecord, context: ExecutionContext) -> dict[str, Any]:
        if self.executor is None:
            return {"ok": False, "reason": "no_executor"}
        if self.tool_registry is not None and self.tool_registry.get(self.writeback_tool) is None:
            return {"ok": False, "reason": "tool_not_registered"}

        step = PlanStep(
            step_id=1,
            action=f"写回案例库（{record.outcome}）",
            tool_name=self.writeback_tool,
            arguments=record.to_writeback_payload(),
            description="M1-6 反思反哺：把处置轨迹写回案例库",
        )
        try:
            result = self.executor.execute(step, context)
        except Exception as exc:  # noqa: BLE001
            logger.warning("incident writeback failed: %s", exc)
            return {"ok": False, "reason": f"{type(exc).__name__}: {exc}"}
        return {
            "ok": bool(result.success),
            "tool": self.writeback_tool,
            "error": result.error,
        }


__all__ = ["IncidentClosure", "IncidentRecord", "WRITEBACK_TOOL"]
