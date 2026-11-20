"""M1 闭环测试：证据融合视图、重复调用守卫、记忆写回与反思收尾。"""

import asyncio

import pytest

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.executor.models import ExecutionContext
from agent.memory.long_term import LongTermMemory
from agent.planner.closure import IncidentClosure
from agent.planner.evidence import EVIDENCE_TOOL_NAMES, EvidenceBundle
from agent.planner.react_planner import ReActPlanner
from agent.policies.policy_engine import PolicyEngine
from agent.sdk.model import ModelProvider, ModelResponse
from agent.sdk.tool import PluginTool, ToolDefinition
from agent.tools.registry import ToolRegistry


# ---------------------------------------------------------------------------
# 测试基础设施
# ---------------------------------------------------------------------------


class ScriptedProvider(ModelProvider):
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
    def __init__(self, name: str, payload):
        self.calls = 0
        self.payload = payload
        self.definition = ToolDefinition(
            name=name,
            description="感知证据",
            risk="LOW",
            input_schema={
                "type": "object",
                "properties": {
                    "metric": {"type": "string"},
                    "nodes": {"type": "array", "items": {"type": "object"}},
                    "logs": {"type": "array", "items": {"type": "object"}},
                    "query": {"type": "string"},
                },
            },
        )

    async def execute(self, arguments, context):
        self.calls += 1
        return self.payload


class WritebackTool(PluginTool):
    def __init__(self):
        self.calls = []
        self.definition = ToolDefinition(
            name="nn.learn_from_incident", description="案例写回", risk="LOW"
        )

    async def execute(self, arguments, context):
        self.calls.append(arguments)
        return {"ok": True, "mode": "learned"}


def _registry(*tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _executor(registry):
    policy = ExecutionPolicy(max_retries=0, sleep_fn=lambda s: None)
    return AgentExecutor(registry, PolicyEngine(), execution_policy=policy)


def _context():
    return ExecutionContext("request-1", "user-1")


def _planner(provider, registry, **kwargs):
    return ReActPlanner(provider, registry, _executor(registry), **kwargs)


def _full_evidence_tools():
    return (
        EvidenceTool(
            "nn.anomaly",
            {"ok": True, "model_status": "ok",
             "results": [{"metric": "memory", "peak_score": 0.93, "span_count": 2}]},
        ),
        EvidenceTool(
            "nn.rootcause",
            {"ok": True, "model_status": "ok",
             "candidates": [{"rank": 1, "alert_id": "a1", "score": 0.88}]},
        ),
        EvidenceTool(
            "nn.log_classify",
            {"ok": True, "num_total": 5, "num_kept": 2,
             "label_distribution": {"oom": 2, "noise": 3}},
        ),
        EvidenceTool(
            "nn.retrieve",
            {"ok": True, "results": [{"incident_key": "c-1", "category": "oom",
                                      "outcome": "resolved", "score": 0.81}]},
        ),
    )


_FOUR_ACTIONS = [
    'Thought: 看指标\nAction: nn.anomaly\nAction Input: {"metric": "memory"}',
    'Thought: 定根因\nAction: nn.rootcause\nAction Input: {"nodes": [{"alert_id": "a1"}]}',
    'Thought: 看日志\nAction: nn.log_classify\nAction Input: {"logs": [{"text": "OOM killed"}]}',
    'Thought: 查案例\nAction: nn.retrieve\nAction Input: {"query": "redis 内存溢出"}',
    "Final Answer: 根因是 a1 内存溢出，建议扩容后重启。",
]


# ---------------------------------------------------------------------------
# M1-2 证据融合
# ---------------------------------------------------------------------------


def test_evidence_bundle_normalizes_four_sources():
    bundle = EvidenceBundle()
    for tool in _full_evidence_tools():
        output = asyncio.run(tool.execute({}, _context()))
        bundle.add(tool.name, output)

    assert bundle.missing() == []
    assert bundle.has_usable() is True
    assert bundle.items["nn.anomaly"].score == 0.93
    assert bundle.items["nn.rootcause"].top_k[0]["alert_id"] == "a1"
    assert bundle.items["nn.log_classify"].score == 0.4
    assert bundle.items["nn.retrieve"].top_k[0]["incident_key"] == "c-1"

    text = bundle.render()
    assert "nn.anomaly" in text
    assert "峰值异常分 0.93" in text


def test_evidence_bundle_marks_unavailable_and_missing():
    bundle = EvidenceBundle()
    bundle.add("nn.anomaly", {"ok": False, "model_status": "unavailable", "error": "down"})
    bundle.add("nn.trace", {"ok": True})  # 非证据工具，忽略

    assert "nn.anomaly" in bundle.missing()
    assert "nn.trace" not in bundle.items
    text = bundle.render()
    assert "缺失" in text
    assert "禁止编造" in text or "不要假设" in text
    assert set(bundle.to_dict()["missing"]) == set(EVIDENCE_TOOL_NAMES)


def test_evidence_view_injected_into_prompt():
    tools = _full_evidence_tools()
    provider = ScriptedProvider([_FOUR_ACTIONS[0], "Final Answer: 完成。"])
    planner = _planner(provider, _registry(*tools))

    planner.run("排查 redis 抖动", _context())

    # 第二轮 Prompt 必须带统一证据视图，而不是只有裸 Observation
    assert "证据统一视图" in provider.prompts[1]
    assert "peak_score" not in provider.prompts[1] or "峰值异常分" in provider.prompts[1]


# ---------------------------------------------------------------------------
# M1-3 重复调用守卫
# ---------------------------------------------------------------------------


def test_duplicate_call_is_blocked_and_counted():
    tool = EvidenceTool("nn.anomaly", {"ok": True, "results": []})
    provider = ScriptedProvider([
        'Thought: 先看指标\nAction: nn.anomaly\nAction Input: {"metric": "cpu"}',
        'Thought: 再看一次\nAction: nn.anomaly\nAction Input: {"metric": "cpu"}',
        "Final Answer: 完成。",
    ])
    planner = _planner(provider, _registry(tool))

    result = planner.run("排查", _context())

    assert result.status == "completed"
    assert tool.calls == 1                       # 第二次被拦截，未真正执行
    assert result.trajectory[1].duplicate is True
    assert result.metadata["stats"] == {"tool_calls": 1, "duplicate_calls": 1}


def test_same_tool_different_args_still_executes():
    tool = EvidenceTool("nn.anomaly", {"ok": True, "results": []})
    provider = ScriptedProvider([
        'Thought: 看 cpu\nAction: nn.anomaly\nAction Input: {"metric": "cpu"}',
        'Thought: 看 memory\nAction: nn.anomaly\nAction Input: {"metric": "memory"}',
        "Final Answer: 完成。",
    ])
    planner = _planner(provider, _registry(tool))

    result = planner.run("排查", _context())

    assert tool.calls == 2
    assert result.metadata["stats"]["duplicate_calls"] == 0


# ---------------------------------------------------------------------------
# M1-4 / M1-5 / M1-6 收尾：反思 + 记忆写回 + 案例库写回
# ---------------------------------------------------------------------------


def test_incident_closure_writes_memory_and_case_library():
    tools = _full_evidence_tools()
    writeback = WritebackTool()
    registry = _registry(*tools, writeback)
    provider = ScriptedProvider(_FOUR_ACTIONS)
    planner = _planner(provider, registry)

    result = planner.run("排查 redis 抖动", _context())
    # 只有统一 Runtime 的后置状态核验通过，才允许归档为 resolved。
    result.metadata["verification_status"] = "verified"
    memory = LongTermMemory()
    closure = IncidentClosure(
        memory, executor=_executor(registry), tool_registry=registry, reflector=None
    )

    record = closure.close("排查 redis 抖动", result, _context())

    assert record.outcome == "resolved"
    assert record.category == "oom"
    assert record.root_cause == "a1"
    assert record.metrics["tool_calls"] == 4

    saved = memory.get(f"incident:{record.incident_key}", owner="user-1")
    assert saved is not None
    assert saved.value["outcome"] == "resolved"

    assert len(writeback.calls) == 1
    payload = writeback.calls[0]
    assert payload["category"] == "oom"
    assert payload["outcome"] == "resolved"
    assert payload["action_taken"] == "wait_and_observe"
    assert record.metrics["writeback"]["ok"] is True


def test_incident_closure_without_executor_skips_writeback():
    tools = _full_evidence_tools()
    provider = ScriptedProvider(_FOUR_ACTIONS)
    planner = _planner(provider, _registry(*tools))
    result = planner.run("排查 redis 抖动", _context())

    closure = IncidentClosure(LongTermMemory(), enable_writeback=True)
    record = closure.close("排查 redis 抖动", result, _context())

    assert record.metrics["writeback"]["ok"] is False
    assert record.metrics["writeback"]["reason"] == "no_executor"


@pytest.mark.parametrize("overrides", [{}, {"success": True}, {"outcome": "resolved"}])
def test_unverified_completion_is_never_written_as_resolved(overrides):
    tools = _full_evidence_tools()
    provider = ScriptedProvider(_FOUR_ACTIONS)
    planner = _planner(provider, _registry(*tools))
    result = planner.run("排查 redis 抖动", _context())
    memory = LongTermMemory()
    closure = IncidentClosure(memory, enable_writeback=False)

    record = closure.close("排查 redis 抖动", result, _context(), **overrides)

    assert record.outcome == "mitigated"
    saved = memory.get(f"incident:{record.incident_key}", owner="user-1")
    assert saved is not None
    assert saved.value["outcome"] == "mitigated"
