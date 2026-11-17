"""P3 Orchestrator 核心：任务分解 → 子 Agent 匹配 → 并发执行 → 结果整合。

核心原则（避免伪多 Agent）：
  1. 每个子 Agent 有独立 system_prompt + 独立 tool_names 白名单
  2. 执行层走 ai-service 的 /api/nn/*（direct mode: 直接 import service；http mode: 真实 HTTP）
  3. 结果整合做冲突检测——不同 Agent 可能给矛盾建议，Orchestrator 必须标注
  4. EventBus 用于子 Agent 间通信（AnomalySleuth 发现 spike → 发 event → RootCauseHunter 收到后加 focus）
"""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from ..kernel.registry.registry import KernelRegistry
from ..kernel.event.bus import EventBus
from .models import (
    AgentProfile,
    AgentSpecialty,
    SubTask,
    SubTaskResult,
    OrchestrationPlan,
)
from .dispatcher import decompose_goal
from .presets import ALL_PRESET_AGENTS, SPECIALTY_INDEX

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.registry = registry or KernelRegistry()
        self.event_bus = event_bus or EventBus()
        self.mode = mode
        self.nn_base_url = nn_base_url
        self.max_concurrency = max(1, max_concurrency)

        # 内置 direct mode 执行器（lazy import，避免 ai-service 不可用时崩）
        self._direct_executor = self._try_init_direct_executor()

        # 注册预设 Agent Profile
        self._register_presets()

    # ------------------------------------------------------------------
    # 初始化
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
        """完整协同闭环。

        同步接口（方便调用），内部用 ThreadPoolExecutor 并发跑子 Agent。
        """
        context = context or {}

        # 1. 任务分解
        subtasks = decompose_goal(goal, context)
        if not subtasks:
            return OrchestrationPlan(goal=goal, overall_status="failed", final_synthesis="无法分解 goal")

        # 2. 子 Agent 匹配 + 过滤
        enabled_set = set(enable_agents) if enable_agents else None
        excluded_set = set(exclude_agents) if exclude_agents else None
        matched_tasks = []
        for task in subtasks:
            profile = SPECIALTY_INDEX.get(task.required_specialty.value)
            if profile is None:
                logger.warning("no preset agent for specialty=%s, skip task=%s", task.required_specialty, task.task_id)
                continue
            if enabled_set and profile.agent_id not in enabled_set:
                continue
            if excluded_set and profile.agent_id in excluded_set:
                continue
            matched_tasks.append((task, profile))

        if not matched_tasks:
            return OrchestrationPlan(goal=goal, overall_status="failed", final_synthesis="没有可用的子 Agent")

        plan = OrchestrationPlan(goal=goal, subtasks=[t for t, _ in matched_tasks])

        # 3. 并发执行（用 ThreadPoolExecutor；direct executor 是 sync）
        executor = self._direct_executor
        if executor is None:
            plan.overall_status = "failed"
            plan.final_synthesis = "direct executor 未初始化，ai-service 不可用"
            return plan

        def _run_task(pair):
            task, profile = pair
            start = time.time()
            try:
                result_data = executor.execute(profile, task, context)
                return SubTaskResult(
                    task_id=task.task_id,
                    agent_id=profile.agent_id,
                    success=True,
                    summary=result_data.get("summary", ""),
                    findings=result_data.get("findings", {}),
                    duration_ms=int((time.time() - start) * 1000),
                )
            except Exception as exc:
                logger.exception("orchestrate task failed: task=%s agent=%s", task.task_id, profile.agent_id)
                return SubTaskResult(
                    task_id=task.task_id,
                    agent_id=profile.agent_id,
                    success=False,
                    error=str(exc),
                    duration_ms=int((time.time() - start) * 1000),
                )

        with ThreadPoolExecutor(max_workers=self.max_concurrency) as pool:
            results = list(pool.map(_run_task, matched_tasks))

        plan.results = results

        # 4. 冲突检测 + 整合
        plan.conflict_notes = self._detect_conflicts(results)
        plan.final_synthesis = self._synthesize(goal, results, context)

        successes = sum(1 for r in results if r.success)
        if successes == len(results):
            plan.overall_status = "completed"
        elif successes > 0:
            plan.overall_status = "partial"
        else:
            plan.overall_status = "failed"

        return plan

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
        context: dict[str, Any],
    ) -> str:
        """把各 Agent 结果整合成一段人类可读的总结（规则，不依赖 LLM）。"""
        parts: list[str] = [f"## 协同目标\n{goal}\n"]

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]

        parts.append(f"## 执行概览\n成功 {len(successes)}/{len(results)}，失败 {len(failures)}\n")

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
                parts.append(f"- {r.agent_id}: {r.error}")
            parts.append("")

        if self._last_plan and self._last_plan.conflict_notes:
            parts.append("## 冲突检测")
            for note in self._last_plan.conflict_notes:
                parts.append(f"- ⚠ {note}")
            parts.append("")

        return "\n".join(parts)

    # 让 _synthesize 能访问 conflict_notes
    _last_plan: OrchestrationPlan | None = None


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
