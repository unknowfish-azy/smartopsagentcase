"""P0 执行闭环加固测试：错误分类、参数校验、超时/重试/死循环检测/失败分级、模型降级链。"""

import asyncio

import pytest

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep
from agent.policies.policy_engine import PolicyEngine
from agent.providers.model.fallback import AllModelsFailedError, FallbackModelProvider
from agent.providers.model.mock import MockModelProvider
from agent.sdk.model import ModelProvider
from agent.sdk.tool import PluginTool, ToolDefinition
from agent.tools.errors import (
    ToolErrorCategory,
    ToolExecutionError,
    classify_exception,
)
from agent.tools.registry import ToolRegistry
from agent.tools.validation import truncate_output, validate_arguments


class FlakyNetworkTool(PluginTool):
    """前 N 次抛网络错误，之后成功；idempotency 默认 SAFE_RETRY 可重试。"""

    def __init__(self, fail_times: int = 1, name: str = "net.call"):
        self.fail_times = fail_times
        self.calls = 0
        self.definition = ToolDefinition(
            name=name,
            description="网络调用",
            input_schema={
                "type": "object",
                "properties": {"target": {"type": "string"}},
                "required": ["target"],
            },
        )

    async def execute(self, arguments, context):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("upstream reset")
        return {"ok": True, "target": arguments["target"]}


class WriteNetworkTool(PluginTool):
    """AT_MOST_ONCE 写操作：网络错误也不允许自动重试。"""

    def __init__(self):
        self.calls = 0
        self.definition = ToolDefinition(
            name="db.write",
            description="写库",
            risk="LOW",
            idempotency="AT_MOST_ONCE",
        )

    async def execute(self, arguments, context):
        self.calls += 1
        raise ConnectionError("connection lost during commit")


class StuckTool(PluginTool):
    def __init__(self, deadline_ms: int = 200):
        self.definition = ToolDefinition(
            name="stuck.call",
            description="卡死工具",
            deadline_ms=deadline_ms,
        )

    async def execute(self, arguments, context):
        import time

        time.sleep(1.0)
        return {"ok": True}


class BusinessFailTool(PluginTool):
    def __init__(self):
        self.calls = 0
        self.definition = ToolDefinition(name="biz.op", description="业务失败工具")

    async def execute(self, arguments, context):
        self.calls += 1
        return {"success": False, "error": "磁盘水位超阈值"}


class BigOutputTool(PluginTool):
    def __init__(self):
        self.definition = ToolDefinition(
            name="log.dump",
            description="大输出工具",
            output_limit_bytes=64,
        )

    async def execute(self, arguments, context):
        return {"log": "x" * 1000}


def _executor(tools, policy=None):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return AgentExecutor(registry, PolicyEngine(), execution_policy=policy)


def _run(tool, arguments=None):
    executor = _executor([tool])
    step = PlanStep(1, "执行", tool.definition.name, arguments or {})
    return executor.execute(step, ExecutionContext("request-1", "user-1"))


# ---------------------------------------------------------------------------
# 错误分类与参数校验
# ---------------------------------------------------------------------------


def test_error_category_mapping():
    assert classify_exception(ConnectionError("x")).category == ToolErrorCategory.NETWORK
    assert classify_exception(PermissionError("x")).category == ToolErrorCategory.PERMISSION
    assert classify_exception(KeyError("x")).category == ToolErrorCategory.RESOURCE_NOT_FOUND
    assert classify_exception(ValueError("x")).category == ToolErrorCategory.PARAMETER
    assert classify_exception(RuntimeError("x")).category == ToolErrorCategory.UNKNOWN
    assert classify_exception(TimeoutError("x")).category == ToolErrorCategory.TIMEOUT


def test_missing_required_param_rejected_without_execution():
    tool = FlakyNetworkTool()
    result = _run(tool, {})

    assert result.success is False
    assert result.error_category == ToolErrorCategory.PARAMETER.value
    assert result.metadata["failure_class"] == "fatal"
    assert tool.calls == 0  # 参数错误不允许触达真实工具


def test_unknown_param_rejected():
    tool = FlakyNetworkTool()
    result = _run(tool, {"target": "a", "evil_extra": 1})

    assert result.success is False
    assert "evil_extra" in (result.error or "")


def test_wrong_param_type_rejected():
    tool = FlakyNetworkTool()
    result = _run(tool, {"target": 123})

    assert result.success is False
    assert result.error_category == ToolErrorCategory.PARAMETER.value


def test_validate_arguments_supports_enum_and_nested():
    schema = {
        "type": "object",
        "properties": {
            "level": {"type": "string", "enum": ["low", "high"]},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["level"],
    }
    validate_arguments(schema, {"level": "low", "tags": ["a"]})
    with pytest.raises(ToolExecutionError):
        validate_arguments(schema, {"level": "medium"})
    with pytest.raises(ToolExecutionError):
        validate_arguments(schema, {"level": "low", "tags": [1]})


def test_validate_arguments_supports_union_type():
    schema = {
        "type": "object",
        "properties": {"parent_id": {"type": ["string", "null"]}},
    }
    validate_arguments(schema, {"parent_id": "root"})
    validate_arguments(schema, {"parent_id": None})
    with pytest.raises(ToolExecutionError):
        validate_arguments(schema, {"parent_id": 123})


# ---------------------------------------------------------------------------
# 超时 / 重试 / 死循环 / 失败分级
# ---------------------------------------------------------------------------


def test_retry_with_backoff_then_success():
    sleeps = []
    policy = ExecutionPolicy(max_retries=2, backoff_base_seconds=0.5, sleep_fn=sleeps.append)
    tool = FlakyNetworkTool(fail_times=1)

    result = _run_with_policy(tool, policy, {"target": "svc-a"})

    assert result.success is True
    assert result.metadata["attempts"] == 2
    assert sleeps == [0.5]  # 第一次重试退避 0.5s，指数基数生效


def test_write_tool_never_retried():
    policy = ExecutionPolicy(max_retries=3, sleep_fn=lambda s: None)
    tool = WriteNetworkTool()

    result = _run_with_policy(tool, policy, {})

    assert result.success is False
    assert result.error_category == ToolErrorCategory.NETWORK.value
    assert tool.calls == 1  # AT_MOST_ONCE：写操作绝不自动重试


def test_stuck_tool_killed_by_deadline():
    policy = ExecutionPolicy(max_retries=0, sleep_fn=lambda s: None)
    tool = StuckTool(deadline_ms=200)

    result = _run_with_policy(tool, policy, {})

    assert result.success is False
    assert result.error_category == ToolErrorCategory.TIMEOUT.value
    assert result.metadata["timeout_ms"] == 200


def _run_with_policy(tool, policy, arguments):
    executor = _executor([tool], policy)
    step = PlanStep(1, "执行", tool.definition.name, arguments)
    return executor.execute(step, ExecutionContext("request-1", "user-1"))


def test_business_failure_is_recoverable_not_fatal():
    tool = BusinessFailTool()
    result = _run(tool, {})

    assert result.success is False
    assert result.error_category == ToolErrorCategory.BUSINESS.value
    assert result.metadata["failure_class"] == "recoverable"


def test_fatal_failure_aborts_plan():
    executor = _executor([FlakyNetworkTool()])
    steps = [
        PlanStep(1, "参数错误步骤", "net.call", {}),  # 缺必填参数 → fatal
        PlanStep(2, "正常步骤", "net.call", {"target": "b"}),
    ]
    context = ExecutionContext("request-1", "user-1")

    plan_result = executor.execute_plan(steps, context)

    assert plan_result.status == "aborted_fatal"
    # 致命失败后后续步骤不再执行
    assert len(plan_result.step_results) == 1


def test_dead_loop_detection_aborts_plan():
    tool = BusinessFailTool()
    executor = _executor([tool])
    steps = [PlanStep(i, "重复失败", "biz.op", {"same": "args"}) for i in range(1, 4)]
    context = ExecutionContext("request-1", "user-1")

    plan_result = executor.execute_plan(steps, context)

    assert plan_result.status == "aborted_loop"
    assert "死循环" in (plan_result.reason or "")


def test_max_rounds_exceeded():
    tool = BusinessFailTool()
    policy = ExecutionPolicy(max_rounds=2, sleep_fn=lambda s: None)
    executor = _executor([tool], policy)
    steps = [PlanStep(i, "步骤", "biz.op", {"k": i}) for i in range(1, 6)]
    context = ExecutionContext("request-1", "user-1")

    plan_result = executor.execute_plan(steps, context)

    assert plan_result.status == "max_rounds_exceeded"
    assert len(plan_result.step_results) == 2


def test_recoverable_failure_continues_plan():
    flaky = FlakyNetworkTool(fail_times=1, name="net.first")  # 网络错误重试后成功
    biz = BusinessFailTool()
    good = FlakyNetworkTool(name="net.second")
    executor = _executor([flaky, biz, good])
    steps = [
        PlanStep(1, "成功", "net.first", {"target": "a"}),
        PlanStep(2, "业务失败", "biz.op", {}),
        PlanStep(3, "恢复", "net.second", {"target": "c"}),
    ]
    context = ExecutionContext("request-1", "user-1")

    plan_result = executor.execute_plan(steps, context)

    assert plan_result.status == "completed"
    assert len(plan_result.step_results) == 3
    assert plan_result.step_results[2].success is True


# ---------------------------------------------------------------------------
# 输出预算
# ---------------------------------------------------------------------------


def test_oversized_output_truncated():
    tool = BigOutputTool()
    result = _run(tool, {})

    assert result.success is True
    assert result.metadata["truncated"] is True
    assert isinstance(result.output, dict)
    assert "已截断" in result.output["note"]
    assert len(result.output["output"]) <= 64 + 1  # 截断标记外的正文不超过预算


def test_truncate_output_small_string_untouched():
    out, truncated = truncate_output("hello", 1024)
    assert out == "hello"
    assert truncated is False


# ---------------------------------------------------------------------------
# 模型降级链
# ---------------------------------------------------------------------------


class FailingProvider(ModelProvider):
    name = "failing"

    async def generate(self, prompt, **kwargs):
        raise RuntimeError("primary down")


def test_fallback_chain_switches_to_backup():
    chain = FallbackModelProvider([FailingProvider(), MockModelProvider("backup")])

    response = asyncio.run(chain.generate("ping"))

    assert response.model == "backup"
    assert response.metadata["fallback_used"] is True
    assert chain.chain == ["failing", "backup"]


def test_fallback_chain_all_failed():
    chain = FallbackModelProvider([FailingProvider(), FailingProvider()])

    with pytest.raises(AllModelsFailedError) as exc_info:
        asyncio.run(chain.generate("ping"))

    assert len(exc_info.value.errors) == 2


def test_fallback_chain_primary_success_no_fallback_flag():
    chain = FallbackModelProvider([MockModelProvider("primary"), MockModelProvider("backup")])

    response = asyncio.run(chain.generate("ping"))

    assert response.model == "primary"
    assert response.metadata["fallback_used"] is False
