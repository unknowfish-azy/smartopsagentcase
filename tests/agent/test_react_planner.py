"""ReAct Planner 测试：Reasoning+Acting 循环、幻觉自纠正、高危审批、降级兜底。"""

import pytest

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.executor.models import ExecutionContext
from agent.planner.react_planner import ReActPlanner
from agent.policies.policy_engine import PolicyEngine
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
        return ModelResponse(content=item, model="scripted", provider="scripted", metadata={})


class EvidenceTool(PluginTool):
    """模拟 /api/nn/* 感知工具：返回结构化证据。"""

    def __init__(self, name: str = "nn.anomaly", risk: str = "LOW", payload=None):
        self.calls = 0
        self.definition = ToolDefinition(
            name=name, description="时序异常检测", risk=risk,
            input_schema={"type": "object", "properties": {"metric": {"type": "string"}}},
        )
        self.payload = payload if payload is not None else {"is_anomaly": True, "anomaly_score": 0.87}

    async def execute(self, arguments, context):
        self.calls += 1
        return self.payload


class WriteTool(PluginTool):
    """高危变更工具。"""

    def __init__(self, name: str = "server.restart", risk: str = "HIGH"):
        self.calls = 0
        self.definition = ToolDefinition(name=name, description="重启服务", risk=risk)

    async def execute(self, arguments, context):
        self.calls += 1
        return {"restarted": True}


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _executor(registry):
    policy = ExecutionPolicy(max_retries=0, sleep_fn=lambda s: None)
    return AgentExecutor(registry, PolicyEngine(), execution_policy=policy)


def _planner(provider, registry, max_iterations=8):
    return ReActPlanner(
        provider, registry, _executor(registry), max_iterations=max_iterations
    )


def _context():
    return ExecutionContext("request-1", "user-1")


# ---------------------------------------------------------------------------
# 完整 ReAct 循环
# ---------------------------------------------------------------------------


def test_final_answer_without_any_tool():
    provider = ScriptedProvider(["Final Answer: 根因是 redis 内存溢出，建议扩容。"])
    planner = _planner(provider, _registry(EvidenceTool()))

    result = planner.run("排查 redis 抖动", _context())

    assert result.status == "completed"
    assert result.success is True
    assert "redis 内存溢出" in result.final_answer
    assert result.plan.planner == "react"
    assert result.plan.steps == []  # 未执行任何工具


def test_action_observation_then_final_answer():
    evidence = EvidenceTool()
    provider = ScriptedProvider([
        "Thought: 先看 redis_cpu 是否异常\nAction: nn.anomaly\nAction Input: {\"metric\": \"redis_cpu\"}",
        "Final Answer: redis_cpu 异常分 0.87，根因是缓存穿透。",
    ])
    planner = _planner(provider, _registry(evidence))

    result = planner.run("排查 redis 抖动", _context())

    assert result.status == "completed"
    assert evidence.calls == 1                       # 工具被真实执行
    assert len(result.trajectory) == 2               # 一轮 Action + 一轮 Final Answer
    assert result.trajectory[0].action == "nn.anomaly"
    assert result.trajectory[0].success is True
    assert "0.87" in result.trajectory[0].observation  # 证据进入 Observation
    assert len(result.plan.steps) == 1               # 执行步骤折算成计划
    # 第二轮 prompt 必须携带上一轮的 Observation（证据喂回模型）
    assert "Observation" in provider.prompts[1]
    assert "0.87" in provider.prompts[1]


def test_think_blocks_and_markdown_labels_are_normalized():
    evidence = EvidenceTool()
    provider = ScriptedProvider([
        "<think>Final Answer: 思考中的草稿不能当结论</think>\n"
        "**Thought**: 先取证据\n**Action**: nn.anomaly\n"
        "**Action Input**: {\"metric\": \"redis_cpu\"}",
        "<think>内部推理</think>\n**Final Answer**: 正式结论，不包含思考标签。",
    ])
    planner = _planner(provider, _registry(evidence))

    result = planner.run("目标", _context())

    assert result.status == "completed"
    assert evidence.calls == 1
    assert result.final_answer == "正式结论，不包含思考标签。"
    assert "草稿" not in result.final_answer


def test_hallucinated_tool_self_corrects():
    provider = ScriptedProvider([
        "Thought: 调用不存在的工具\nAction: nn.not_exist\nAction Input: {}",
        "Thought: 改用真实工具\nAction: nn.anomaly\nAction Input: {\"metric\": \"redis_cpu\"}",
        "Final Answer: 已定位根因。",
    ])
    evidence = EvidenceTool()
    planner = _planner(provider, _registry(evidence))

    result = planner.run("目标", _context())

    assert result.status == "completed"
    assert result.trajectory[0].success is False      # 幻觉工具名被拒
    assert "不存在" in result.trajectory[0].observation
    assert evidence.calls == 1                        # 纠正后真实工具被调用一次


def test_unparsable_output_gives_one_retry():
    provider = ScriptedProvider([
        "我完全不知道该干什么",                      # 无法解析 → 纠错机会
        "Final Answer: 已给出结论。",
    ])
    planner = _planner(provider, _registry(EvidenceTool()))

    result = planner.run("目标", _context())

    assert result.status == "completed"
    assert result.final_answer == "已给出结论。"


# ---------------------------------------------------------------------------
# 安全红线：高危工具暂停自主循环
# ---------------------------------------------------------------------------


def test_high_risk_tool_pauses_for_approval():
    write = WriteTool()
    provider = ScriptedProvider([
        "Thought: 需要重启 redis\nAction: server.restart\nAction Input: {\"service\": \"redis\"}",
    ])
    planner = _planner(provider, _registry(write))

    result = planner.run("重启 redis", _context())

    assert result.status == "needs_approval"
    assert write.calls == 0                           # 高危工具未被执行
    assert result.metadata["pending_tool"] == "server.restart"
    assert result.plan.requires_human_approval is True


def test_high_risk_tool_allowed_in_dry_run():
    write = WriteTool()
    provider = ScriptedProvider([
        "Thought: dry-run 重启\nAction: server.restart\nAction Input: {\"service\": \"redis\"}",
        "Final Answer: dry-run 完成。",
    ])
    planner = _planner(provider, _registry(write))
    context = ExecutionContext("r", "u", dry_run=True)

    result = planner.run("重启 redis", context)

    assert result.status == "completed"               # dry_run 下可执行


# ---------------------------------------------------------------------------
# 边界与降级
# ---------------------------------------------------------------------------


def test_max_iterations_returns_partial_trajectory():
    provider = ScriptedProvider([
        "Thought: 再看一个指标\nAction: nn.anomaly\nAction Input: {}",
    ] * 3)
    planner = _planner(provider, _registry(EvidenceTool()), max_iterations=3)

    result = planner.run("目标", _context())

    assert result.status == "max_iterations"
    assert result.success is False
    assert len(result.trajectory) == 3
    assert "最大轮次" in result.metadata["reason"]


def test_model_error_falls_back_to_rule_planner():
    provider = ScriptedProvider([RuntimeError("primary down")])
    planner = _planner(provider, _registry(EvidenceTool()))

    result = planner.run("重启 nginx", _context())

    assert result.status == "rule-fallback"
    assert result.plan.planner == "rule-fallback"
    assert result.plan.metadata["fallback_reason"]
    assert len(result.plan.steps) >= 1                # 规则 Planner 兜底产出


def test_observation_is_truncated_to_budget():
    big = EvidenceTool(payload={"data": "x" * 5000})
    provider = ScriptedProvider([
        "Thought: 查证据\nAction: nn.anomaly\nAction Input: {}",
        "Final Answer: 完成。",
    ])
    planner = ReActPlanner(
        provider, _registry(big), _executor(_registry(big)), observation_budget=100
    )

    result = planner.run("目标", _context())

    observation = result.trajectory[0].observation
    assert len(observation) < 200
    assert "截断" in observation


def test_create_plan_alias_matches_run():
    provider = ScriptedProvider(["Final Answer: 结论。"])
    planner = _planner(provider, _registry(EvidenceTool()))

    result = planner.create_plan("目标", _context())

    assert result.status == "completed"
    assert result.plan.planner == "react"
