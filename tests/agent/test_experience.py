"""P5 失败复盘沉淀测试：ExperienceSink 的 payload、fail-open 语义与 PlanRunner 接线。

只验证"上报了什么、失败是否被吞掉、何时上报"：
后端 recordLearned 的幂等与置信度逻辑由 OperatorMemoryServiceTest 负责。
"""

import json
from urllib import error as urllib_error
from urllib import request as urllib_request

from agent.executor.executor import PlanExecutionResult
from agent.executor.result import ExecutionResult
from agent.planner.experience import (
    EXPERIENCE_ENDPOINT,
    ExperienceSink,
    incident_key_from_goal,
    lesson_from_outcome,
)
from agent.planner.runner import PlanRunner
from agent.reflection.reflection import ReflectionVerdict

BASE = "http://127.0.0.1:8080"
TOKEN = "test-internal-token"
HEADER = "X-SmartOps-Internal-Token"


class _FakeResponse:
    def __init__(self, payload: dict | bytes, status: int = 200) -> None:
        self.status = status
        self._body = (
            payload if isinstance(payload, bytes)
            else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        )

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc_info) -> bool:
        return False


def _failed_result(step_id=1, tool="doomed.op", error="不可恢复的故障", category="BUSINESS"):
    return PlanExecutionResult(
        status="completed",
        step_results=[
            ExecutionResult(
                success=False, tool_name=tool, message="失败",
                error=error, error_category=category,
                metadata={"step_id": step_id},
            )
        ],
        reason="1 步失败",
    )


def _outcome(status="failed", plan_ids=None, result=None, reason="失败"):
    from agent.planner.runner import RunOutcome

    outcome = RunOutcome(
        goal="排查 nginx 502", success=False, status=status, reason=reason,
        plan_ids=plan_ids or ["abc123-r1"],
        plan_results=[result] if result is not None else [_failed_result()],
    )
    return outcome


def _install(monkeypatch, *, handler=None, env=True):
    """装载 urlopen mock 并设置 env；返回记录到的请求列表。"""
    requests = []

    def fake_urlopen(request, timeout=None):
        requests.append(request)
        if handler is not None:
            return handler(request)
        return _FakeResponse({"code": 0, "data": {"id": 7}})

    monkeypatch.setattr(urllib_request, "urlopen", fake_urlopen)
    if env:
        monkeypatch.setenv("SMARTOPS_BACKEND_URL", BASE)
        monkeypatch.setenv("SMARTOPS_INTERNAL_TOKEN", TOKEN)
    else:
        monkeypatch.delenv("SMARTOPS_BACKEND_URL", raising=False)
        monkeypatch.delenv("SMARTOPS_INTERNAL_TOKEN", raising=False)
    return requests


# ---------------------------------------------------------------------------
# 纯函数：incident_key 与教训句
# ---------------------------------------------------------------------------


def test_incident_key_strips_verb_prefix_and_truncates():
    assert incident_key_from_goal("排查 nginx 502") == "nginx 502"
    assert incident_key_from_goal("帮我处理 docker 容器反复重启") == "docker 容器反复重启"
    assert incident_key_from_goal("请检查 disk full") == "disk full"
    long = incident_key_from_goal("排查 " + "a" * 100)
    assert len(long) == 40


def test_lesson_from_outcome_contains_failure_details():
    outcome = _outcome()
    lesson = lesson_from_outcome(outcome)
    assert "doomed.op" in lesson
    assert "BUSINESS" in lesson
    assert "不可恢复的故障" in lesson
    assert "人工" in lesson  # 明示需人工核实，不是可自动执行的指令


# ---------------------------------------------------------------------------
# ExperienceSink.report
# ---------------------------------------------------------------------------


def test_report_posts_failure_experience(monkeypatch):
    requests = _install(monkeypatch)
    sink = ExperienceSink()
    assert sink.report(_outcome(), user_id="81") is True

    assert len(requests) == 1
    request = requests[0]
    assert request.full_url == BASE + EXPERIENCE_ENDPOINT
    assert TOKEN in request.headers.values()  # 鉴权头必须带
    payload = json.loads(request.data.decode("utf-8"))
    assert payload["userId"] == 81
    assert payload["incidentKey"] == "nginx 502"
    assert "doomed.op" in payload["preferredAction"]
    assert payload["sourceRefs"] == "PLAN_RUN:abc123-r1"


def test_report_skips_completed_runs(monkeypatch):
    requests = _install(monkeypatch)
    sink = ExperienceSink()
    assert sink.report(_outcome(status="completed"), user_id="81") is False
    assert requests == []


def test_report_skips_non_numeric_user_id(monkeypatch):
    requests = _install(monkeypatch)
    sink = ExperienceSink()
    assert sink.report(_outcome(), user_id=None) is False
    assert sink.report(_outcome(), user_id="anon-user") is False
    assert requests == []


def test_report_fails_open_without_config(monkeypatch):
    requests = _install(monkeypatch, env=False)
    sink = ExperienceSink()
    assert sink.report(_outcome(), user_id="81") is False
    assert requests == []


def test_report_swallows_http_and_network_errors(monkeypatch):
    def http_fail(request):
        raise urllib_error.HTTPError(BASE + EXPERIENCE_ENDPOINT, 500, "boom", None, None)

    def network_fail(request):
        raise urllib_error.URLError("refused")

    for handler in (http_fail, network_fail):
        requests = _install(monkeypatch, handler=handler)
        sink = ExperienceSink()
        assert sink.report(_outcome(), user_id="81") is False
        assert len(requests) == 1  # 尝试过，但异常被吞掉


def test_report_swallows_unexpected_sink_crash(monkeypatch):
    def crash(request):
        raise RuntimeError("unexpected")

    requests = _install(monkeypatch, handler=crash)
    sink = ExperienceSink()
    assert sink.report(_outcome(), user_id="81") is False
    assert len(requests) == 1


def test_report_skips_empty_incident_key(monkeypatch):
    requests = _install(monkeypatch)
    sink = ExperienceSink()
    outcome = _outcome()
    outcome.goal = "   "
    assert sink.report(outcome, user_id="81") is False
    assert requests == []


def test_on_run_finished_pulls_user_id_from_context(monkeypatch):
    requests = _install(monkeypatch)

    class _Context:
        user_id = "81"

    sink = ExperienceSink()
    assert sink.on_run_finished(_outcome(), _Context()) is True
    assert len(requests) == 1


# ---------------------------------------------------------------------------
# PlanRunner 接线
# ---------------------------------------------------------------------------


class _FakePlanner:
    planner = "rule"

    def create_plan(self, goal, failure_context=None):
        return type("Plan", (), {"steps": [], "planner": "rule"})()


class _FailingExecutor:
    def execute_plan(self, steps, context, policy=None, plan_store=None, plan_id=None):
        return _failed_result()


class _SuccessExecutor:
    def execute_plan(self, steps, context, policy=None, plan_store=None, plan_id=None):
        return PlanExecutionResult(status="completed", step_results=[], reason="ok")


class _StopReflector:
    """非 replan 裁决：走 status=failed 终止分支。"""

    def review(self, goal, plan_result):
        return ReflectionVerdict(decision="fail", reason="无需重规划")


class _ReplanReflector:
    """一直要求重规划：走 reflection_budget_exhausted 终止分支。"""

    def review(self, goal, plan_result):
        return ReflectionVerdict(decision="replan", reason="仍失败", failed_step_ids=[1])


class _RecordingSink:
    def __init__(self):
        self.calls = []

    def on_run_finished(self, outcome, context):
        self.calls.append((outcome.status, getattr(context, "user_id", None)))


class _Context:
    user_id = "81"


def test_runner_reports_failure_to_sink():
    sink = _RecordingSink()
    runner = PlanRunner(_FakePlanner(), _FailingExecutor(), reflector=_StopReflector(),
                        max_execution_rounds=2, experience_sink=sink)
    outcome = runner.run("排查 nginx 502", _Context())
    assert outcome.status == "failed"
    assert [status for status, _ in sink.calls] == ["failed"]
    assert sink.calls[0][1] == "81"


def test_runner_reports_budget_exhaustion_to_sink():
    sink = _RecordingSink()
    runner = PlanRunner(_FakePlanner(), _FailingExecutor(), reflector=_ReplanReflector(),
                        max_execution_rounds=2, experience_sink=sink)
    outcome = runner.run("排查 nginx 502", _Context())
    assert outcome.status == "reflection_budget_exhausted"
    assert [status for status, _ in sink.calls] == ["reflection_budget_exhausted"]


def test_runner_success_does_not_report():
    sink = _RecordingSink()
    runner = PlanRunner(_FakePlanner(), _SuccessExecutor(), max_execution_rounds=2,
                        experience_sink=sink)
    outcome = runner.run("排查 nginx 502", _Context())
    assert outcome.success is True
    assert sink.calls == []


def test_runner_swallows_sink_crash():
    class _CrashingSink:
        def on_run_finished(self, outcome, context):
            raise RuntimeError("sink down")

    runner = PlanRunner(_FakePlanner(), _FailingExecutor(), reflector=_StopReflector(),
                        max_execution_rounds=1, experience_sink=_CrashingSink())
    outcome = runner.run("排查 nginx 502", _Context())
    assert outcome.status == "failed"  # 主链路不受影响


def test_runner_without_sink_still_works():
    runner = PlanRunner(_FakePlanner(), _FailingExecutor(), reflector=_StopReflector(),
                        max_execution_rounds=1)
    outcome = runner.run("排查 nginx 502", _Context())
    assert outcome.status == "failed"
