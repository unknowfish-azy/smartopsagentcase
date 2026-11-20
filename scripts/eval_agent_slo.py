"""Agent SLO 确定性故障注入基准，输出 JSON 明细、Markdown 报表与发布门禁。

运行真实 Orchestrator / ReActPlanner 控制流，但子 Agent、模型与工具均为内存脚本
替身；不访问网络、数据库或外部模型。场景与响应固定，墙钟延迟和 trace_id 除外。

用法：
    python scripts/eval_agent_slo.py
    python scripts/eval_agent_slo.py --repetitions 30 \
        --output-json data/lake/_eval/agent_slo.json \
        --output-md data/lake/_eval/agent_slo.md

注意：这是控制流可靠性与调度开销基准，不是生产流量 SLO，也不证明真实模型
质量或真实模型/API 延迟。故障场景里的失败和跳过是预期行为，只有符合契约才通过。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import platform
import statistics
import sys
import threading
import time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from agent.executor.models import ExecutionContext  # noqa: E402
from agent.executor.result import ExecutionResult  # noqa: E402
from agent.orchestrator import Orchestrator, OrchestratorPolicy  # noqa: E402
from agent.planner.react_planner import ReActPlanner  # noqa: E402
from agent.sdk.model import ModelProvider, ModelResponse  # noqa: E402
from agent.sdk.tool import PluginTool, ToolDefinition  # noqa: E402
from agent.tools.registry import ToolRegistry  # noqa: E402

GOAL = "生产故障：CPU 指标异常，请定位根因、检索历史案例并给出处置建议"
DOWNSTREAM_TASKS = ("t_rootcause_hunter", "t_case_retriever", "t_action_advisor")
ORCHESTRATION_SCENARIOS = (
    "normal_dag",
    "dependency_failure",
    "timeout_isolation",
    "retry_recovery",
    "retry_exhaustion",
)
REACT_SCENARIOS = ("react_duplicate_guard", "react_distinct_arguments")
SCENARIOS = ORCHESTRATION_SCENARIOS + REACT_SCENARIOS


@dataclass
class Observation:
    """一次场景运行的可审计原始记录。零分母指标保持 None，不伪造为 0。"""

    scenario_id: str
    family: str
    repetition: int
    passed: bool
    status: str
    duration_ms: float
    task_count: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    attempted: int = 0
    retried: int = 0
    timed_out: int = 0
    waves: int = 0
    tool_calls: int = 0
    duplicate_calls: int = 0
    actual_tool_calls: int = 0
    trace_id: str | None = None
    failures: list[str] = field(default_factory=list)
    signals: dict[str, int] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)


class ScriptedOrchestrationExecutor:
    """按场景返回固定证据或注入故障，不调用任何真实子 Agent 服务。"""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.calls: list[dict[str, Any]] = []
        self.anomaly_attempts = 0
        self.upstream_ok = False
        self.case_query_ok = False
        self._lock = threading.Lock()

    def execute(self, profile, task, context) -> dict[str, Any]:
        specialty = profile.specialty.value
        with self._lock:
            self.calls.append({"task_id": task.task_id, "specialty": specialty})
            if specialty == "anomaly_sleuth":
                self.anomaly_attempts += 1
                attempt = self.anomaly_attempts
            else:
                attempt = 1

        if specialty == "anomaly_sleuth":
            if self.scenario == "timeout_isolation":
                time.sleep(0.06)
            if self.scenario in {"dependency_failure", "retry_exhaustion"}:
                raise RuntimeError("scripted anomaly backend failure")
            if self.scenario == "retry_recovery" and attempt == 1:
                raise RuntimeError("scripted transient anomaly failure")
            return {
                "summary": "发现 CPU 异常片段",
                "findings": {"metric": "cpu", "spans": [{"start": 10, "end": 20}]},
            }
        if specialty == "rootcause_hunter":
            upstream = context.get("upstream") or {}
            self.upstream_ok = upstream.get("t_anomaly_sleuth", {}).get("findings", {}).get("metric") == "cpu"
            return {
                "summary": "根因候选为 db-proxy",
                "findings": {"confidence": 0.92, "top_candidates": ["db-proxy"]},
            }
        if specialty == "case_retriever":
            self.case_query_ok = "db-proxy" in context.get("query", "")
            return {
                "summary": "命中相似历史案例",
                "findings": {"top_resolved_case": {"action_taken": "scale_out"}},
            }
        if specialty == "action_advisor":
            return {
                "summary": "推荐扩容并观察",
                "findings": {"top_recommendation": {"action": "scale_out", "risk_score": 0.1}},
            }
        return {"summary": f"{specialty} 完成", "findings": {"ok": True}}


def _run_orchestration(scenario: str, repetition: int) -> Observation:
    started = time.perf_counter()
    executor = ScriptedOrchestrationExecutor(scenario)
    max_retries = {"retry_recovery": 1, "retry_exhaustion": 2}.get(scenario, 0)
    timeout_seconds = 0.02 if scenario == "timeout_isolation" else 2.0
    orchestrator = Orchestrator(
        executor=executor,
        policy=OrchestratorPolicy(
            max_concurrency=3,
            task_timeout_seconds=timeout_seconds,
            max_task_retries=max_retries,
            retry_backoff_seconds=0,
            sleep_fn=lambda _: None,
        ),
    )
    plan = orchestrator.orchestrate(GOAL)
    results = {result.task_id: result for result in plan.results}
    anomaly = results["t_anomaly_sleuth"]
    expected_status = "completed" if scenario in {"normal_dag", "retry_recovery"} else "partial"
    checks: dict[str, bool] = {
        "overall_status": plan.overall_status == expected_status,
        "five_tasks": plan.metrics["task_count"] == 5,
        "four_waves": plan.metrics["waves"] == 4,
        "trace_on_plan": bool(plan.trace_id),
        "trace_on_results": all(result.trace_id == plan.trace_id for result in plan.results),
        "retry_budget": anomaly.attempts <= max_retries + 1,
    }

    signals: dict[str, int] = {
        "execution_calls": len(executor.calls),
        "retry_budget_violations": int(anomaly.attempts > max_retries + 1),
    }
    if scenario in {"normal_dag", "retry_recovery"}:
        checks.update(
            all_succeeded=all(result.success for result in plan.results),
            upstream_evidence=executor.upstream_ok,
            upstream_query=executor.case_query_ok,
        )
        signals.update(upstream_required=1, upstream_injected=int(executor.upstream_ok))
    if scenario == "retry_recovery":
        recovered = anomaly.success and anomaly.attempts == 2 and plan.metrics["retried"] == 1
        checks["bounded_retry_recovered"] = recovered
        signals.update(recovery_expected=1, recovery_observed=int(recovered))
    if scenario in {"dependency_failure", "timeout_isolation", "retry_exhaustion"}:
        called_tasks = {call["task_id"] for call in executor.calls}
        checks.update(
            downstream_skipped=all(results[task_id].skipped for task_id in DOWNSTREAM_TASKS),
            downstream_not_executed=all(task_id not in called_tasks for task_id in DOWNSTREAM_TASKS),
            independent_log_succeeded=results["t_log_interpreter"].success,
            skip_section_in_synthesis="## 跳过项" in plan.final_synthesis,
        )
        signals.update(
            downstream_expected=len(DOWNSTREAM_TASKS),
            downstream_skipped=sum(results[task_id].skipped for task_id in DOWNSTREAM_TASKS),
            isolation_peer_expected=1,
            isolation_peer_succeeded=int(results["t_log_interpreter"].success),
        )
    if scenario == "dependency_failure":
        checks["execution_error_classified"] = anomaly.error_category == "EXECUTION"
    if scenario == "timeout_isolation":
        timed_out = anomaly.error_category == "TIMEOUT" and plan.metrics["timed_out"] == 1
        checks["timeout_isolated"] = timed_out
        signals.update(timeout_expected=1, timeout_observed=int(timed_out))
    if scenario == "retry_exhaustion":
        checks["retry_exhausted_at_bound"] = anomaly.attempts == 3 and not anomaly.success

    failures = [name for name, passed in checks.items() if not passed]
    return Observation(
        scenario_id=scenario,
        family="orchestration",
        repetition=repetition,
        passed=not failures,
        status=plan.overall_status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        task_count=plan.metrics["task_count"],
        succeeded=plan.metrics["succeeded"],
        failed=plan.metrics["failed"],
        skipped=plan.metrics["skipped"],
        attempted=plan.metrics["attempted"],
        retried=plan.metrics["retried"],
        timed_out=plan.metrics["timed_out"],
        waves=plan.metrics["waves"],
        tool_calls=len(executor.calls),
        actual_tool_calls=len(executor.calls),
        trace_id=plan.trace_id,
        failures=failures,
        signals=signals,
        details={
            "anomaly_attempts": anomaly.attempts,
            "plan_total_ms": plan.metrics["total_ms"],
            "skipped_task_ids": [result.task_id for result in plan.results if result.skipped],
        },
    )


class ScriptedProvider(ModelProvider):
    """有限响应脚本；响应耗尽立即失败，避免静默循环。"""

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)

    @property
    def name(self) -> str:
        return "slo-scripted"

    async def generate(self, prompt: str, **kwargs) -> ModelResponse:
        if not self.responses:
            raise RuntimeError("scripted provider exhausted")
        return ModelResponse(
            content=self.responses.pop(0),
            model="slo-scripted",
            provider="slo-scripted",
            metadata={},
        )


class CountingEvidenceTool(PluginTool):
    def __init__(self) -> None:
        self.calls = 0
        self.definition = ToolDefinition(
            name="nn.anomaly",
            description="内存异常证据工具",
            risk="LOW",
            input_schema={
                "type": "object",
                "properties": {"metric": {"type": "string"}},
                "required": ["metric"],
            },
        )

    async def execute(self, arguments, context) -> dict[str, Any]:
        self.calls += 1
        return {
            "ok": True,
            "model_status": "scripted",
            "results": [{"metric": arguments["metric"], "peak_score": 0.9, "span_count": 1}],
        }


class InProcessToolExecutor:
    """ReAct 所需的最小执行适配器；直接执行内存工具，无审计/DB 副作用。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, step, context) -> ExecutionResult:
        tool = self.registry.get(step.tool_name)
        try:
            output = asyncio.run(tool.execute(step.arguments, context))
            return ExecutionResult(True, step.tool_name, "ok", output=output)
        except Exception as exc:  # 让 ReAct 轨迹记录真实脚本错误
            return ExecutionResult(False, step.tool_name, "failed", error=str(exc))


def _run_react(scenario: str, repetition: int) -> Observation:
    started = time.perf_counter()
    first = 'Thought: 获取 CPU 证据\nAction: nn.anomaly\nAction Input: {"metric": "cpu"}'
    if scenario == "react_duplicate_guard":
        responses = [first, first, "Final Answer: 已基于现有证据完成研判。"]
    else:
        responses = [
            first,
            'Thought: 获取内存证据\nAction: nn.anomaly\nAction Input: {"metric": "memory"}',
            "Final Answer: 两路不同参数证据均已完成研判。",
        ]
    provider = ScriptedProvider(responses)
    tool = CountingEvidenceTool()
    registry = ToolRegistry()
    registry.register(tool)
    planner = ReActPlanner(
        provider,
        registry,
        InProcessToolExecutor(registry),
        max_iterations=5,
        llm_timeout_seconds=2,
    )
    context = ExecutionContext(f"slo-{scenario}-{repetition}", "slo-benchmark")
    result = planner.run("排查指标异常", context)
    stats = result.metadata.get("stats", {})
    expected_calls = 1 if scenario == "react_duplicate_guard" else 2
    expected_duplicates = 1 if scenario == "react_duplicate_guard" else 0
    checks = {
        "completed": result.status == "completed" and result.success,
        "tool_call_count": stats.get("tool_calls") == expected_calls,
        "actual_tool_call_count": tool.calls == expected_calls,
        "duplicate_count": stats.get("duplicate_calls") == expected_duplicates,
        "plan_steps": len(result.plan.steps) == expected_calls,
    }
    if scenario == "react_duplicate_guard":
        checks["duplicate_marked"] = any(step.duplicate for step in result.trajectory)
    failures = [name for name, passed in checks.items() if not passed]
    return Observation(
        scenario_id=scenario,
        family="react",
        repetition=repetition,
        passed=not failures,
        status=result.status,
        duration_ms=round((time.perf_counter() - started) * 1000, 3),
        tool_calls=stats.get("tool_calls", 0),
        duplicate_calls=stats.get("duplicate_calls", 0),
        actual_tool_calls=tool.calls,
        failures=failures,
        signals={
            "duplicate_attempts": expected_duplicates,
            "duplicates_blocked": stats.get("duplicate_calls", 0),
            "execution_calls": tool.calls,
        },
        details={"iterations": len(result.trajectory)},
    )


RUNNERS: dict[str, Callable[[str, int], Observation]] = {
    **{name: _run_orchestration for name in ORCHESTRATION_SCENARIOS},
    **{name: _run_react for name in REACT_SCENARIOS},
}


def ratio(numerator: int | float, denominator: int | float) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def percentile(values: list[float], q: float) -> float | None:
    """与现有 eval_chat_latency.py 一致的线性插值分位数。"""

    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 3)


def _latency(observations: list[Observation]) -> dict[str, Any]:
    values = [row.duration_ms for row in observations]
    return {
        "sample_count": len(values),
        "p50": percentile(values, 0.50),
        "p95": percentile(values, 0.95),
        "p99": percentile(values, 0.99),
        "mean": round(statistics.fmean(values), 3) if values else None,
        "min": round(min(values), 3) if values else None,
        "max": round(max(values), 3) if values else None,
    }


def _summarize_scenario(scenario: str, rows: list[Observation]) -> dict[str, Any]:
    signals = Counter()
    for row in rows:
        signals.update(row.signals)
    signal_dict = dict(signals)
    task_count = sum(row.task_count for row in rows)
    attempted = sum(row.attempted for row in rows)
    trace_expected = len(rows) if rows and rows[0].family == "orchestration" else 0
    trace_observed = sum(bool(row.trace_id) for row in rows)
    return {
        "family": rows[0].family,
        "runs": len(rows),
        "passed_runs": sum(row.passed for row in rows),
        "conformance_rate": ratio(sum(row.passed for row in rows), len(rows)),
        "status_counts": dict(Counter(row.status for row in rows)),
        "latency_ms": _latency(rows),
        "tasks": {
            "total": task_count,
            "succeeded": sum(row.succeeded for row in rows),
            "failed": sum(row.failed for row in rows),
            "skipped": sum(row.skipped for row in rows),
            "attempted": attempted,
            "retried": sum(row.retried for row in rows),
            "timed_out": sum(row.timed_out for row in rows),
            "success_rate": ratio(sum(row.succeeded for row in rows), task_count),
            "attempted_success_rate": ratio(sum(row.succeeded for row in rows), attempted),
            "skip_rate": ratio(sum(row.skipped for row in rows), task_count),
            "timeout_rate": ratio(sum(row.timed_out for row in rows), attempted),
        },
        "average_waves": round(statistics.fmean(row.waves for row in rows), 3) if rows else None,
        "tool_calls": sum(row.tool_calls for row in rows),
        "duplicate_calls": sum(row.duplicate_calls for row in rows),
        "actual_tool_calls": sum(row.actual_tool_calls for row in rows),
        "trace_coverage": ratio(trace_observed, trace_expected),
        "signals": signal_dict,
        "rates": {
            "downstream_skip": ratio(signal_dict.get("downstream_skipped", 0), signal_dict.get("downstream_expected", 0)),
            "timeout_detection": ratio(signal_dict.get("timeout_observed", 0), signal_dict.get("timeout_expected", 0)),
            "isolation_peer_success": ratio(signal_dict.get("isolation_peer_succeeded", 0), signal_dict.get("isolation_peer_expected", 0)),
            "retry_recovery": ratio(signal_dict.get("recovery_observed", 0), signal_dict.get("recovery_expected", 0)),
            "upstream_injection": ratio(signal_dict.get("upstream_injected", 0), signal_dict.get("upstream_required", 0)),
            "duplicate_block": ratio(signal_dict.get("duplicates_blocked", 0), signal_dict.get("duplicate_attempts", 0)),
        },
    }


def _merge_rates(scenarios: dict[str, dict[str, Any]], names: tuple[str, ...], rate_name: str) -> float | None:
    signal_name = {
        "downstream_skip": ("downstream_skipped", "downstream_expected"),
        "timeout_detection": ("timeout_observed", "timeout_expected"),
        "isolation_peer_success": ("isolation_peer_succeeded", "isolation_peer_expected"),
        "retry_recovery": ("recovery_observed", "recovery_expected"),
        "upstream_injection": ("upstream_injected", "upstream_required"),
        "duplicate_block": ("duplicates_blocked", "duplicate_attempts"),
    }[rate_name]
    numerator = sum(scenarios[name]["signals"].get(signal_name[0], 0) for name in names)
    denominator = sum(scenarios[name]["signals"].get(signal_name[1], 0) for name in names)
    return ratio(numerator, denominator)


def _gate(gate_id: str, metric: str, actual: Any, comparator: str, threshold: float) -> dict[str, Any]:
    if actual is None:
        passed = False
    elif comparator == "gte":
        passed = actual >= threshold
    elif comparator == "lte":
        passed = actual <= threshold
    else:
        raise ValueError(f"unsupported comparator: {comparator}")
    return {
        "gate_id": gate_id,
        "metric": metric,
        "actual": actual,
        "comparator": comparator,
        "threshold": threshold,
        "status": "PASS" if passed else "FAIL",
    }


def run_benchmark(
    repetitions: int = 30,
    *,
    clean_p95_budget_ms: float = 1000.0,
    timeout_p95_budget_ms: float = 500.0,
) -> dict[str, Any]:
    """执行固定场景矩阵并计算门禁；所有计数均可追溯到 observations。"""

    if repetitions < 1:
        raise ValueError("repetitions 必须 >= 1")
    if clean_p95_budget_ms <= 0 or timeout_p95_budget_ms <= 0:
        raise ValueError("延迟预算必须 > 0")

    benchmark_started = time.perf_counter()
    observations = [
        RUNNERS[scenario](scenario, repetition)
        for scenario in SCENARIOS
        for repetition in range(1, repetitions + 1)
    ]
    scenarios = {
        scenario: _summarize_scenario(
            scenario, [row for row in observations if row.scenario_id == scenario]
        )
        for scenario in SCENARIOS
    }
    normal = scenarios["normal_dag"]
    react_duplicate = scenarios["react_duplicate_guard"]
    react_distinct = scenarios["react_distinct_arguments"]
    conformance = ratio(sum(row.passed for row in observations), len(observations))
    retry_violations = sum(row.signals.get("retry_budget_violations", 0) for row in observations)
    downstream_skip = _merge_rates(
        scenarios,
        ("dependency_failure", "timeout_isolation", "retry_exhaustion"),
        "downstream_skip",
    )
    timeout_detection = scenarios["timeout_isolation"]["rates"]["timeout_detection"]
    isolation_peer = _merge_rates(
        scenarios, ("dependency_failure", "timeout_isolation"), "isolation_peer_success"
    )
    retry_recovery = scenarios["retry_recovery"]["rates"]["retry_recovery"]
    upstream_injection = _merge_rates(
        scenarios, ("normal_dag", "retry_recovery"), "upstream_injection"
    )
    duplicate_block = react_duplicate["rates"]["duplicate_block"]

    gates = [
        _gate("all_scenarios_conform", "scenario_conformance_rate", conformance, "gte", 1.0),
        _gate("clean_dag_success", "normal_dag.task_success_rate", normal["tasks"]["success_rate"], "gte", 1.0),
        _gate("clean_dag_trace", "normal_dag.trace_coverage", normal["trace_coverage"], "gte", 1.0),
        _gate("upstream_evidence_injected", "upstream_injection_rate", upstream_injection, "gte", 1.0),
        _gate("dependency_fail_closed", "fault_scenarios.downstream_skip_rate", downstream_skip, "gte", 1.0),
        _gate("timeout_detected", "timeout_isolation.detection_rate", timeout_detection, "gte", 1.0),
        _gate("independent_peer_survives", "fault_scenarios.peer_success_rate", isolation_peer, "gte", 1.0),
        _gate("transient_retry_recovers", "retry_recovery.rate", retry_recovery, "gte", 1.0),
        _gate("retry_budget_bounded", "retry_budget_violations", retry_violations, "lte", 0),
        _gate("duplicate_calls_blocked", "react_duplicate_guard.block_rate", duplicate_block, "gte", 1.0),
        _gate("distinct_arguments_not_overblocked", "react_distinct_arguments.duplicate_calls", react_distinct["duplicate_calls"], "lte", 0),
        _gate("clean_dag_p95_overhead", "normal_dag.latency_ms.p95", normal["latency_ms"]["p95"], "lte", clean_p95_budget_ms),
        _gate("timeout_isolation_p95_overhead", "timeout_isolation.latency_ms.p95", scenarios["timeout_isolation"]["latency_ms"]["p95"], "lte", timeout_p95_budget_ms),
    ]
    status = "PASS" if all(gate["status"] == "PASS" for gate in gates) else "FAIL"
    orchestration_rows = [row for row in observations if row.family == "orchestration"]
    react_rows = [row for row in observations if row.family == "react"]
    task_total = sum(row.task_count for row in orchestration_rows)
    attempted = sum(row.attempted for row in orchestration_rows)
    return {
        "schema_version": "smartops.agent_slo.v1",
        "status": status,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "benchmark": {
            "kind": "deterministic_fault_injection",
            "production_observation": False,
            "real_model_invoked": False,
            "external_calls": False,
            "scenario_count": len(SCENARIOS),
            "repetitions_per_scenario": repetitions,
            "run_count": len(observations),
            "orchestration_run_count": len(orchestration_rows),
            "react_run_count": len(react_rows),
            "wall_clock_ms": round((time.perf_counter() - benchmark_started) * 1000, 3),
            "environment": {"python": platform.python_version(), "platform": platform.platform()},
            "latency_scope": "真实控制流 + 内存脚本替身的本机墙钟开销，不含模型推理、网络或真实工具延迟",
        },
        "thresholds": {
            "clean_dag_p95_ms": clean_p95_budget_ms,
            "timeout_isolation_p95_ms": timeout_p95_budget_ms,
            "all_correctness_rates": 1.0,
            "retry_budget_violations": 0,
            "distinct_argument_duplicate_calls": 0,
        },
        "metrics": {
            "scenario_conformance_rate": conformance,
            "orchestration_task_success_rate": ratio(sum(row.succeeded for row in orchestration_rows), task_total),
            "orchestration_attempted_task_success_rate": ratio(sum(row.succeeded for row in orchestration_rows), attempted),
            "orchestration_skip_rate": ratio(sum(row.skipped for row in orchestration_rows), task_total),
            "orchestration_timeout_rate": ratio(sum(row.timed_out for row in orchestration_rows), attempted),
            "clean_dag_task_success_rate": normal["tasks"]["success_rate"],
            "downstream_skip_rate": downstream_skip,
            "timeout_detection_rate": timeout_detection,
            "independent_peer_success_rate": isolation_peer,
            "retry_recovery_rate": retry_recovery,
            "upstream_injection_rate": upstream_injection,
            "duplicate_block_rate": duplicate_block,
            "duplicate_call_avoidance_rate": ratio(
                react_duplicate["duplicate_calls"],
                react_duplicate["tool_calls"] + react_duplicate["duplicate_calls"],
            ),
            "orchestration_trace_coverage": ratio(
                sum(bool(row.trace_id) for row in orchestration_rows), len(orchestration_rows)
            ),
            "retry_budget_violations": retry_violations,
        },
        "scenarios": scenarios,
        "gates": gates,
        "observations": [asdict(row) for row in observations],
        "limitations": [
            "场景、模型响应和工具结果均为固定脚本；结果证明控制流契约，不证明真实模型准确率。",
            "延迟是内存执行器下的本机墙钟开销，不可作为生产模型/API SLO。",
            "预期故障场景中的失败和跳过不计为评测器失败，但必须完全符合 fail-closed 契约。",
            "生产 SLO 仍需接入真实 trace、模型版本、流量窗口与错误预算后另行计算。",
        ],
    }


def _percent(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.2%}"


def _milliseconds(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def render_markdown(report: dict[str, Any]) -> str:
    """生成答辩可读报表；只引用报告已有观测值，不补造指标。"""

    benchmark = report["benchmark"]
    metrics = report["metrics"]
    normal = report["scenarios"]["normal_dag"]
    timeout = report["scenarios"]["timeout_isolation"]
    duplicate = report["scenarios"]["react_duplicate_guard"]
    lines = [
        "# 智维Agent · Agent SLO 评测报告",
        "",
        f"> 门禁结论：**{report['status']}** ｜ 场景：{benchmark['scenario_count']} 类 × "
        f"{benchmark['repetitions_per_scenario']} 次 = {benchmark['run_count']} 次运行",
        "",
        "## 1. 评测边界",
        "",
        "- 类型：**确定性故障注入基准**，直接运行现有 Orchestrator 与 ReActPlanner 控制流。",
        "- 替身边界：子 Agent、模型响应、工具结果均为内存固定脚本；未调用真实模型、网络或数据库。",
        "- 延迟口径：本机墙钟调度/控制流开销，**不是生产模型或 API 延迟**。",
        "- 故障口径：注入失败、超时、重试与跳过均为预期行为；符合契约才算场景通过。",
        f"- 运行时间（UTC）：`{report['created_at']}`；环境：`{benchmark['environment']['platform']}` / Python {benchmark['environment']['python']}。",
        "",
        "## 2. 核心量化证据",
        "",
        "| 指标 | 观测值 | 样本 / 口径 |",
        "|---|---:|---|",
        f"| 场景契约通过率 | **{_percent(metrics['scenario_conformance_rate'])}** | {benchmark['run_count']} 次场景运行 |",
        f"| 正常 DAG 子任务成功率 | **{_percent(metrics['clean_dag_task_success_rate'])}** | {normal['tasks']['succeeded']}/{normal['tasks']['total']} 个子任务 |",
        f"| 正常 DAG 延迟 P50 / P95 / P99 | **{_milliseconds(normal['latency_ms']['p50'])} / {_milliseconds(normal['latency_ms']['p95'])} / {_milliseconds(normal['latency_ms']['p99'])} ms** | {normal['runs']} 次，仅控制流开销 |",
        f"| 超时隔离延迟 P50 / P95 / P99 | **{_milliseconds(timeout['latency_ms']['p50'])} / {_milliseconds(timeout['latency_ms']['p95'])} / {_milliseconds(timeout['latency_ms']['p99'])} ms** | {timeout['runs']} 次，含 20ms 注入预算 |",
        f"| 故障下游 fail-closed 跳过率 | **{_percent(metrics['downstream_skip_rate'])}** | 三类故障场景，应跳过且实际跳过 |",
        f"| 超时识别率 / 同波独立任务成功率 | **{_percent(metrics['timeout_detection_rate'])} / {_percent(metrics['independent_peer_success_rate'])}** | 超时注入与独立日志任务 |",
        f"| 瞬时故障有界重试恢复率 | **{_percent(metrics['retry_recovery_rate'])}** | 首次失败、第二次成功，最多重试 1 次 |",
        f"| 上游证据注入率 / trace 覆盖率 | **{_percent(metrics['upstream_injection_rate'])} / {_percent(metrics['orchestration_trace_coverage'])}** | 正常及恢复链路 / 全部 DAG 运行 |",
        f"| 重复调用拦截率 / 避免率 | **{_percent(metrics['duplicate_block_rate'])} / {_percent(metrics['duplicate_call_avoidance_rate'])}** | {duplicate['duplicate_calls']} 次重复请求未进入真实工具 |",
        f"| 重试预算违规数 | **{metrics['retry_budget_violations']}** | 所有 DAG 运行，阈值 0 |",
        "",
        "## 3. 分场景结果",
        "",
        "| 场景 | 运行 | 契约通过 | 子任务成功率 | 跳过率 | 超时任务 | 重试任务 | P50 (ms) | P95 (ms) | P99 (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for scenario_id, scenario in report["scenarios"].items():
        tasks = scenario["tasks"]
        lines.append(
            f"| `{scenario_id}` | {scenario['runs']} | {_percent(scenario['conformance_rate'])} | "
            f"{_percent(tasks['success_rate'])} | {_percent(tasks['skip_rate'])} | "
            f"{tasks['timed_out']} | {tasks['retried']} | {_milliseconds(scenario['latency_ms']['p50'])} | "
            f"{_milliseconds(scenario['latency_ms']['p95'])} | {_milliseconds(scenario['latency_ms']['p99'])} |"
        )
    lines.extend([
        "",
        "### 波次、调用与追踪",
        "",
        "| 场景 | 平均波次 | 执行/工具调用 | 实际工具调用 | 重复拦截 | trace 覆盖 |",
        "|---|---:|---:|---:|---:|---:|",
    ])
    for scenario_id, scenario in report["scenarios"].items():
        waves = "N/A" if scenario["family"] == "react" else f"{scenario['average_waves']:.2f}"
        lines.append(
            f"| `{scenario_id}` | {waves} | {scenario['tool_calls']} | "
            f"{scenario['actual_tool_calls']} | {scenario['duplicate_calls']} | "
            f"{_percent(scenario['trace_coverage'])} |"
        )
    lines.extend([
        "",
        "注：Orchestrator 的执行调用包含故障尝试与重试；ReAct 场景没有 DAG 子任务/波次，相关单元格为 N/A。故障场景的成功率下降是注入结果，不能与正常 DAG 成功率混作生产可用率。",
        "",
        "## 4. SLO / 发布门禁",
        "",
        "| 门禁 | 指标 | 实际 | 条件 | 结果 |",
        "|---|---|---:|---:|---|",
    ])
    for gate in report["gates"]:
        comparator = "≥" if gate["comparator"] == "gte" else "≤"
        actual = "N/A" if gate["actual"] is None else f"{gate['actual']:.6g}"
        lines.append(
            f"| `{gate['gate_id']}` | `{gate['metric']}` | {actual} | {comparator} {gate['threshold']:g} | **{gate['status']}** |"
        )
    lines.extend([
        "",
        "## 5. 指标定义与复现",
        "",
        "- 子任务成功率 = 成功子任务数 / 全部子任务数；尝试任务成功率另存于 JSON 的 `attempted_success_rate`。",
        "- 跳过率 = fail-closed 跳过子任务数 / 全部子任务数；超时率 = TIMEOUT 子任务数 / 实际尝试子任务数。",
        "- 重复调用避免率 = 被守卫拦截的重复请求 /（唯一真实调用 + 重复请求）。",
        "- P50/P95/P99 使用排序样本线性插值；零分母指标输出 `null` / N/A，不记为 0。",
        "- JSON `observations` 保留每次运行的 trace、计数、失败断言与延迟，可逐项复算。",
        "",
        "```powershell",
        f"python scripts/eval_agent_slo.py --repetitions {benchmark['repetitions_per_scenario']} --output-json data/lake/_eval/agent_slo.json --output-md data/lake/_eval/agent_slo.md",
        "```",
        "",
        "## 6. 不可外推的结论",
        "",
    ])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def write_reports(report: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repetitions", type=int, default=30, help="每个固定场景的重复次数，默认 30")
    parser.add_argument("--clean-p95-budget-ms", type=float, default=1000.0, help="正常 DAG 控制流 P95 门限")
    parser.add_argument("--timeout-p95-budget-ms", type=float, default=500.0, help="超时隔离控制流 P95 门限")
    parser.add_argument("--output-json", type=Path, default=Path("data/lake/_eval/agent_slo.json"))
    parser.add_argument("--output-md", type=Path, default=Path("data/lake/_eval/agent_slo.md"))
    args = parser.parse_args(argv)
    logging.getLogger("agent.orchestrator").setLevel(logging.CRITICAL)

    report = run_benchmark(
        args.repetitions,
        clean_p95_budget_ms=args.clean_p95_budget_ms,
        timeout_p95_budget_ms=args.timeout_p95_budget_ms,
    )
    write_reports(report, args.output_json, args.output_md)
    print(json.dumps({
        "status": report["status"],
        "scenario_count": report["benchmark"]["scenario_count"],
        "run_count": report["benchmark"]["run_count"],
        "metrics": report["metrics"],
        "failed_gates": [gate["gate_id"] for gate in report["gates"] if gate["status"] == "FAIL"],
        "json": str(args.output_json),
        "markdown": str(args.output_md),
    }, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
