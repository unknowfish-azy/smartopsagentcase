"""P1 测试：LLM Planner、计划持久化/断点续跑、Reflector 反思、PlanRunner 闭环编排。"""

import pytest

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.executor.models import ExecutionContext
from agent.planner.llm_planner import LLMPlanner, extract_json_payload
from agent.planner.persistence import PlanStore
from agent.planner.runner import PlanRunner
from agent.planner.steps import PlanStep
from agent.policies.policy_engine import PolicyEngine
from agent.providers.storage.file import FileStorage
from agent.reflection.reflection import Reflector
from agent.sdk.model import ModelProvider, ModelResponse
from agent.sdk.tool import PluginTool, ToolDefinition
from agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 测试基础设施
# ---------------------------------------------------------------------------


class ScriptedProvider(ModelProvider):
    """按脚本依次返回内容或抛异常的伪模型。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    @property
    def name(self):
        return "scripted"

    async def generate(self, prompt, **kwargs):
        self.prompts.append(prompt)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return ModelResponse(
            content=item, model="scripted", provider="scripted", metadata={}
        )


class OkTool(PluginTool):
    def __init__(self, name: str = "net.call", risk="LOW"):
        self.calls = 0
        self.definition = ToolDefinition(name=name, description="正常工具", risk=risk)

    async def execute(self, arguments, context):
        self.calls += 1
        return {"ok": True}


class FlakyBusinessTool(PluginTool):
    """第一次调用业务失败，之后成功。"""

    def __init__(self, name: str = "flaky.op"):
        self.calls = 0
        self.definition = ToolDefinition(name=name, description="不稳定工具")

    async def execute(self, arguments, context):
        self.calls += 1
        if self.calls == 1:
            return {"success": False, "error": "服务预热中"}
        return {"ok": True}


class AlwaysFailTool(PluginTool):
    def __init__(self, name: str = "doomed.op"):
        self.definition = ToolDefinition(name=name, description="永远失败")

    async def execute(self, arguments, context):
        return {"success": False, "error": "不可恢复的故障"}


PLAN_JSON = (
    '{"steps": ['
    '{"action": "查询状态", "tool_name": "net.call", "arguments": {"target": "svc"},'
    ' "description": "读取状态", "requires_approval": false}]}'
)


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _executor(registry):
    policy = ExecutionPolicy(max_retries=0, sleep_fn=lambda s: None)
    return AgentExecutor(registry, PolicyEngine(), execution_policy=policy)


# ---------------------------------------------------------------------------
# JSON 提取
# ---------------------------------------------------------------------------


def test_extract_json_payload_plain_and_fenced():
    assert extract_json_payload('{"a": 1}') == {"a": 1}
    assert extract_json_payload('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json_payload('好的，计划如下：{"a": 1} 请查收') == {"a": 1}
    assert extract_json_payload("我做不到") is None


# ---------------------------------------------------------------------------
# LLM Planner
# ---------------------------------------------------------------------------


def test_llm_planner_produces_valid_plan():
    provider = ScriptedProvider([PLAN_JSON])
    planner = LLMPlanner(provider, _registry(OkTool()))

    plan = planner.create_plan("检查服务状态")

    assert plan.planner == "llm"
    assert len(plan.steps) == 1
    assert plan.steps[0].tool_name == "net.call"
    assert plan.steps[0].step_id == 1
    assert "工具目录" in provider.prompts[0]
    assert "net.call" in provider.prompts[0]


def test_llm_planner_forces_approval_on_high_risk_tool():
    provider = ScriptedProvider([PLAN_JSON])
    planner = LLMPlanner(provider, _registry(OkTool(risk="HIGH")))

    plan = planner.create_plan("高危目标")

    # 模型说 requires_approval=false，但高危工具强制审批
    assert plan.steps[0].requires_approval is True
    assert plan.requires_human_approval is True


def test_llm_planner_falls_back_on_invalid_json():
    provider = ScriptedProvider(["抱歉，我无法完成该任务"])
    planner = LLMPlanner(provider, _registry(OkTool()))

    plan = planner.create_plan("任意目标")

    assert plan.planner == "rule-fallback"
    assert plan.metadata["fallback_reason"]
    assert len(plan.steps) >= 1  # 规则 Planner 兜底产出


def test_llm_planner_falls_back_on_unknown_tool():
    bad_plan = '{"steps": [{"tool_name": "not.exist", "arguments": {}}]}'
    provider = ScriptedProvider([bad_plan])
    planner = LLMPlanner(provider, _registry(OkTool()))

    plan = planner.create_plan("目标")

    assert plan.planner == "rule-fallback"


def test_llm_planner_falls_back_on_model_error():
    provider = ScriptedProvider([RuntimeError("primary down")])
    planner = LLMPlanner(provider, _registry(OkTool()))

    plan = planner.create_plan("目标")

    assert plan.planner == "rule-fallback"


def test_llm_planner_caps_step_count():
    many = ",".join(
        f'{{"action": "s{i}", "tool_name": "net.call", "arguments": {{}}}}' for i in range(20)
    )
    provider = ScriptedProvider([f'{{"steps": [{many}]}}'])
    planner = LLMPlanner(provider, _registry(OkTool()), max_steps=3)

    plan = planner.create_plan("目标")

    assert plan.planner == "llm"
    assert len(plan.steps) == 3


# ---------------------------------------------------------------------------
# 计划持久化与断点续跑
# ---------------------------------------------------------------------------


def test_plan_store_checkpoints_each_step(tmp_path):
    tool = OkTool()
    executor = _executor(_registry(tool))
    store = PlanStore(FileStorage(tmp_path / "plans"))
    steps = [PlanStep(1, "a", "net.call", {}), PlanStep(2, "b", "net.call", {})]
    context = ExecutionContext("request-1", "user-1")

    store.create("p1", "目标", steps)
    executor.execute_plan(steps, context, plan_store=store, plan_id="p1")

    state = store.load("p1")
    assert state.status == "completed"
    assert state.completed_step_ids == {1, 2}
    assert tool.calls == 2


def test_resume_plan_skips_succeeded_steps(tmp_path):
    tool = OkTool()
    executor1 = _executor(_registry(tool))
    store = PlanStore(FileStorage(tmp_path / "plans"))
    steps = [PlanStep(1, "a", "net.call", {}), PlanStep(2, "b", "net.call", {})]
    context = ExecutionContext("request-1", "user-1")

    # 模拟中断：只执行了第一步就挂掉
    store.create("p1", "目标", steps)
    executor1.execute_plan(steps[:1], context, plan_store=store, plan_id="p1")
    assert tool.calls == 1

    # 服务重启后：新 executor 实例从存储恢复
    executor2 = _executor(_registry(tool)).with_plan_store(store)
    result = executor2.resume_plan("p1", context)

    assert result.success is True
    assert tool.calls == 2  # 第一步没有重复执行
    assert result.step_results[0].metadata["step_id"] == 2


def test_resume_plan_without_store_raises():
    executor = _executor(_registry(OkTool()))
    with pytest.raises(ValueError):
        executor.resume_plan("missing", ExecutionContext("r", "u"))


def test_resume_plan_all_done_short_circuits(tmp_path):
    store = PlanStore(FileStorage(tmp_path / "plans"))
    steps = [PlanStep(1, "a", "net.call", {})]
    store.create("p1", "目标", steps)
    store.record_step("p1", 1, success=True)
    store.finish("p1", "completed")

    executor = _executor(_registry(OkTool())).with_plan_store(store)
    result = executor.resume_plan("p1", ExecutionContext("r", "u"))

    assert result.success is True
    assert result.step_results == []


# ---------------------------------------------------------------------------
# Reflector
# ---------------------------------------------------------------------------


def _plan_result(step_results, status="completed"):
    from agent.executor.result import ExecutionResult
    from agent.executor.executor import PlanExecutionResult

    results = []
    for sid, success, tool, error in step_results:
        results.append(
            ExecutionResult(
                success=success,
                tool_name=tool,
                message="",
                error=error,
                error_category=None if success else "BUSINESS",
                metadata={"step_id": sid, "failure_class": None if success else "recoverable"},
            )
        )
    return PlanExecutionResult(status=status, step_results=results)


def test_reflector_rule_verdict_pass_and_replan():
    reflector = Reflector()
    ok = _plan_result([(1, True, "net.call", None)])
    bad = _plan_result([(1, True, "net.call", None), (2, False, "biz.op", "磁盘满")])

    ok_verdict = reflector.review("目标", ok)
    bad_verdict = reflector.review("目标", bad)

    assert ok_verdict.decision == "pass"
    assert bad_verdict.decision == "replan"
    assert bad_verdict.failed_step_ids == [2]
    assert "磁盘满" in bad_verdict.reason


def test_reflector_llm_verdict_and_fallback():
    provider = ScriptedProvider(['{"decision": "pass", "reason": "已达标", "failed_step_ids": []}'])
    reflector = Reflector(model_provider=provider)
    verdict = reflector.review("目标", _plan_result([(1, True, "net.call", None)]))
    assert verdict.decision == "pass"
    assert verdict.source == "llm"

    provider2 = ScriptedProvider(["看不懂的输出"])
    reflector2 = Reflector(model_provider=provider2)
    verdict2 = reflector2.review("目标", _plan_result([(1, False, "biz.op", "超时")]))
    assert verdict2.decision == "replan"  # 退化规则裁决
    assert verdict2.source == "llm-fallback"


# ---------------------------------------------------------------------------
# PlanRunner 闭环编排
# ---------------------------------------------------------------------------


def test_runner_success_first_round():
    planner = LLMPlanner(ScriptedProvider([PLAN_JSON]), _registry(OkTool()))
    runner = PlanRunner(planner, _executor(_registry(OkTool())))

    outcome = runner.run("目标", ExecutionContext("r", "u"))

    assert outcome.success is True
    assert outcome.status == "completed"
    assert len(outcome.plan_results) == 1
    assert outcome.planner_used == "llm"


def test_runner_replan_then_success():
    provider = ScriptedProvider([PLAN_JSON.replace("net.call", "flaky.op"),
                                 PLAN_JSON.replace("net.call", "flaky.op")])
    planner = LLMPlanner(provider, _registry(FlakyBusinessTool()))
    runner = PlanRunner(planner, _executor(_registry(FlakyBusinessTool())))

    outcome = runner.run("目标", ExecutionContext("r", "u"))

    assert outcome.success is True
    assert len(outcome.plan_results) == 2          # 第一轮失败、第二轮成功
    assert len(outcome.reflections) == 1           # 反思一次后重规划
    assert outcome.reflections[0].decision == "replan"
    assert outcome.status == "completed"


def test_runner_reflection_budget_exhausted():
    provider = ScriptedProvider([PLAN_JSON.replace("net.call", "doomed.op")] * 3)
    planner = LLMPlanner(provider, _registry(AlwaysFailTool()))
    runner = PlanRunner(
        planner, _executor(_registry(AlwaysFailTool())), max_execution_rounds=3,
    )

    outcome = runner.run("目标", ExecutionContext("r", "u"))

    assert outcome.success is False
    assert outcome.status == "reflection_budget_exhausted"
    assert len(outcome.plan_results) == 3
    assert len(outcome.reflections) == 3           # 每轮失败都反思过
    assert "人工介入" in (outcome.reason or "")


def test_runner_reflector_pass_stops_loop():
    # 业务失败但评审员判定达标 → 不再重规划，直接收尾
    provider = ScriptedProvider([PLAN_JSON.replace("net.call", "doomed.op"),
                                 '{"decision": "pass", "reason": "可接受", "failed_step_ids": []}'])
    planner = LLMPlanner(provider, _registry(AlwaysFailTool()))
    reflector = Reflector(model_provider=ScriptedProvider([
        '{"decision": "pass", "reason": "可接受", "failed_step_ids": []}',
    ]))
    runner = PlanRunner(planner, _executor(_registry(AlwaysFailTool())), reflector=reflector)

    outcome = runner.run("目标", ExecutionContext("r", "u"))

    assert outcome.success is False
    assert outcome.status == "failed"
    assert len(outcome.plan_results) == 1          # 评审 pass，不进入第二轮
