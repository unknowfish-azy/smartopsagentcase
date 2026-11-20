"""Orchestrator 企业级可靠性测试。

覆盖：依赖分波顺序、上游证据注入、超时隔离、有界重试、依赖失败跳过、
冲突提示进入最终结论、跨运行无共享状态、trace 与运行指标。
"""

from __future__ import annotations

import time

import pytest

from agent.orchestrator import Orchestrator, OrchestratorPolicy

pytestmark = pytest.mark.agent

GOAL = "生产故障：CPU 指标异常，请定位根因并给出处置建议"


class FakeExecutor:
    """按专长分发的假执行器，记录调用顺序与上下文。"""

    def __init__(self, handlers=None):
        self.handlers = handlers or {}
        self.calls: list[dict] = []

    def execute(self, profile, task, context):
        self.calls.append(
            {
                "specialty": profile.specialty.value,
                "task_id": task.task_id,
                "context": context,
                "at": time.monotonic(),
            }
        )
        handler = self.handlers.get(profile.specialty.value)
        if handler is None:
            return {"summary": f"{profile.agent_id} ok", "findings": {}}
        return handler(task, context)


def _orchestrator(executor: FakeExecutor, **policy_kwargs) -> Orchestrator:
    return Orchestrator(
        executor=executor,
        policy=OrchestratorPolicy(**policy_kwargs),
    )


def _by_specialty(executor: FakeExecutor, specialty: str) -> list[dict]:
    return [c for c in executor.calls if c["specialty"] == specialty]


# ---------------------------------------------------------------------------
# 依赖调度与上游证据
# ---------------------------------------------------------------------------


def test_dependencies_run_in_waves_and_inject_upstream():
    executor = FakeExecutor(
        {
            "anomaly_sleuth": lambda task, ctx: {
                "summary": "发现 2 段 CPU 尖峰",
                "findings": {"spans": [{"start": 10, "end": 20}], "metric": "cpu"},
            },
            "rootcause_hunter": lambda task, ctx: {
                "summary": "根因候选为 db-proxy",
                "findings": {"confidence": 0.82, "top_candidates": ["db-proxy"]},
            },
        }
    )

    plan = _orchestrator(executor, task_timeout_seconds=5).orchestrate(GOAL)

    assert plan.overall_status == "completed"
    assert plan.metrics["success_rate"] == 1.0

    # 依赖顺序：anomaly 必须先于 rootcause，rootcause 必须先于 case/action
    anomaly_at = _by_specialty(executor, "anomaly_sleuth")[0]["at"]
    rootcause_call = _by_specialty(executor, "rootcause_hunter")[0]
    assert rootcause_call["at"] >= anomaly_at
    case_at = _by_specialty(executor, "case_retriever")[0]["at"]
    action_at = _by_specialty(executor, "action_advisor")[0]["at"]
    assert case_at >= rootcause_call["at"]
    assert action_at >= case_at

    # 上游证据注入下游上下文（而非各跑各的）
    upstream = rootcause_call["context"].get("upstream") or {}
    assert "t_anomaly_sleuth" in upstream
    assert upstream["t_anomaly_sleuth"]["findings"]["metric"] == "cpu"

    # 案例检索的 query 由上游证据拼出，让 depends_on 真正影响检索
    case_query = _by_specialty(executor, "case_retriever")[0]["context"].get("query", "")
    assert "db-proxy" in case_query


# ---------------------------------------------------------------------------
# 冲突提示必须进入最终结论（原实现在 synthesis 时读不到 conflict_notes）
# ---------------------------------------------------------------------------


def test_conflict_notes_reach_final_synthesis():
    executor = FakeExecutor(
        {
            "anomaly_sleuth": lambda task, ctx: {
                "summary": "检测到异常 span",
                "findings": {"spans": [{"start": 1, "end": 3}]},
            },
            "rootcause_hunter": lambda task, ctx: {
                "summary": "置信度偏低",
                "findings": {"confidence": 0.0},
            },
            "case_retriever": lambda task, ctx: {
                "summary": "历史案例",
                "findings": {"top_resolved_case": {"action_taken": "restart"}},
            },
            "action_advisor": lambda task, ctx: {
                "summary": "当前推荐",
                "findings": {"top_recommendation": {"action": "scale_out"}},
            },
        }
    )

    plan = _orchestrator(executor).orchestrate(GOAL)

    assert len(plan.conflict_notes) == 2
    assert "## 冲突检测" in plan.final_synthesis
    for note in plan.conflict_notes:
        assert note in plan.final_synthesis


# ---------------------------------------------------------------------------
# 超时隔离
# ---------------------------------------------------------------------------


def test_slow_subtask_is_isolated_and_does_not_block_others():
    def slow_anomaly(task, ctx):
        time.sleep(0.4)
        return {"summary": "慢任务完成", "findings": {}}

    executor = FakeExecutor({"anomaly_sleuth": slow_anomaly})
    plan = _orchestrator(
        executor, task_timeout_seconds=0.08, max_task_retries=0
    ).orchestrate(GOAL)

    results = {r.task_id: r for r in plan.results}
    anomaly = results["t_anomaly_sleuth"]
    assert anomaly.success is False
    assert anomaly.error_category == "TIMEOUT"

    # 同波日志解读不受慢任务影响
    assert results["t_log_interpreter"].success is True
    # 依赖异常检测的下游按 fail-closed 跳过
    assert results["t_rootcause_hunter"].skipped is True
    assert results["t_case_retriever"].skipped is True
    assert plan.overall_status == "partial"
    assert plan.metrics["timed_out"] == 1


# ---------------------------------------------------------------------------
# 有界重试
# ---------------------------------------------------------------------------


def test_transient_failure_is_retried_within_budget():
    attempts = {"count": 0}

    def flaky(task, ctx):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("temporary glitch")
        return {"summary": "重试后成功", "findings": {"ok": True}}

    executor = FakeExecutor({"anomaly_sleuth": flaky})
    plan = _orchestrator(executor, max_task_retries=1).orchestrate(GOAL)

    anomaly = next(r for r in plan.results if r.task_id == "t_anomaly_sleuth")
    assert anomaly.success is True
    assert anomaly.attempts == 2
    assert plan.metrics["retried"] == 1
    assert plan.overall_status == "completed"


def test_failed_dependency_skips_downstream_without_calling_it():
    def always_fail(task, ctx):
        raise RuntimeError("model unavailable")

    executor = FakeExecutor({"anomaly_sleuth": always_fail})
    plan = _orchestrator(executor, max_task_retries=0).orchestrate(GOAL)

    results = {r.task_id: r for r in plan.results}
    assert results["t_anomaly_sleuth"].success is False
    for task_id in ("t_rootcause_hunter", "t_case_retriever", "t_action_advisor"):
        assert results[task_id].skipped is True
        assert results[task_id].error_category == "DEPENDENCY"

    # 被跳过的子 Agent 不应产生执行调用
    called = {c["task_id"] for c in executor.calls}
    assert "t_rootcause_hunter" not in called
    assert "t_case_retriever" not in called
    assert "t_action_advisor" not in called

    assert "## 跳过项" in plan.final_synthesis
    assert plan.overall_status == "partial"


# ---------------------------------------------------------------------------
# 跨运行无共享状态 / 运行元数据
# ---------------------------------------------------------------------------


def test_runs_do_not_share_conflict_state():
    executor = FakeExecutor(
        {
            "anomaly_sleuth": lambda task, ctx: {
                "summary": "有异常",
                "findings": {"spans": [{"start": 0, "end": 1}]},
            },
            "rootcause_hunter": lambda task, ctx: {
                "summary": "低置信",
                "findings": {"confidence": 0.0},
            },
        }
    )
    orchestrator = _orchestrator(executor)

    first = orchestrator.orchestrate(GOAL)
    assert first.conflict_notes

    # 第二次运行换成完全无冲突的产出，不得继承上一次的冲突提示
    executor.handlers = {
        "anomaly_sleuth": lambda task, ctx: {"summary": "无异常", "findings": {"spans": []}},
        "rootcause_hunter": lambda task, ctx: {
            "summary": "高置信",
            "findings": {"confidence": 0.9},
        },
    }
    second = orchestrator.orchestrate(GOAL)

    assert second.conflict_notes == []
    assert "## 冲突检测" not in second.final_synthesis
    assert second.trace_id and second.trace_id != first.trace_id


def test_plan_exposes_trace_and_metrics():
    executor = FakeExecutor()
    plan = _orchestrator(executor).orchestrate(GOAL)

    assert len(plan.trace_id) == 16
    assert plan.metrics["trace_id"] == plan.trace_id
    assert plan.metrics["task_count"] == len(plan.subtasks)
    assert plan.metrics["waves"] == 4
    assert plan.metrics["succeeded"] == len(plan.subtasks)
    assert plan.metrics["success_rate"] == 1.0

    payload = plan.to_dict()
    assert payload["trace_id"] == plan.trace_id
    assert payload["metrics"]["total_ms"] >= 0
    assert payload["results"][0]["trace_id"] == plan.trace_id
