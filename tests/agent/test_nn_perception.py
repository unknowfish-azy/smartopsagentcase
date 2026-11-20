"""神经网络感知工具测试：payload 构造、参数校验、服务不可达兜底、注册与执行集成。"""

import asyncio

import pytest

from agent.executor.executor import AgentExecutor, ExecutionPolicy
from agent.executor.models import ExecutionContext
from agent.planner.steps import PlanStep
from agent.policies.policy_engine import PolicyEngine
from agent.tools.builtin.nn_perception import (
    AnomalyDetectTool,
    CaseRetrieveTool,
    LogClassifyTool,
    RootCauseTool,
    build_nn_perception_tools,
)
from agent.tools.registry import ToolRegistry


class FakeHttp:
    """记录调用并按端点返回预设响应的 fake POST。"""

    def __init__(self, responses=None, error=None):
        self.responses = responses or {}
        self.error = error
        self.calls = []  # [(url, payload)]

    async def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.error is not None:
            raise self.error
        for endpoint, resp in self.responses.items():
            if endpoint in url:
                return resp
        return {"ok": True}


def _run(tool, args):
    return asyncio.run(tool.execute(args, ExecutionContext("r", "u")))


# ---------------------------------------------------------------------------
# payload 构造 + URL 路由
# ---------------------------------------------------------------------------


def test_anomaly_payload_and_url():
    http = FakeHttp({"/api/nn/anomaly": {"ok": True, "model_status": "ok", "results": []}})
    tool = AnomalyDetectTool(base_url="http://127.0.0.1:8001", http_post=http)

    result = _run(tool, {"values": [1.0, 2.0, 3.0], "metric_name": "redis_cpu", "window": 64})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url == "http://127.0.0.1:8001/api/nn/anomaly"
    assert payload["values"] == [1.0, 2.0, 3.0]
    assert payload["metric_name"] == "redis_cpu"
    assert payload["window"] == 64


def test_rootcause_payload_and_url():
    http = FakeHttp({"/api/nn/rootcause": {"ok": True, "candidates": [{"alert_id": "a1", "score": 0.9}]}})
    tool = RootCauseTool(base_url="http://127.0.0.1:8001", http_post=http)
    nodes = [{"alert_id": "a1", "severity": "P0"}, {"alert_id": "a2"}]

    result = _run(tool, {"nodes": nodes, "top_k": 3})

    assert result["candidates"][0]["alert_id"] == "a1"
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/rootcause")
    assert payload["nodes"] == nodes
    assert payload["top_k"] == 3


def test_log_classify_payload_and_url():
    http = FakeHttp({"/api/nn/log-classify": {"ok": True, "num_kept": 1, "results": []}})
    tool = LogClassifyTool(base_url="http://127.0.0.1:8001", http_post=http)
    logs = [{"text": "OOM killed"}, {"text": "heartbeat ok"}]

    result = _run(tool, {"logs": logs, "filter_noise": True})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/log-classify")
    assert payload["logs"] == logs
    assert payload["filter_noise"] is True


def test_retrieve_payload_and_url():
    http = FakeHttp({"/api/nn/retrieve": {"ok": True, "cases": []}})
    tool = CaseRetrieveTool(base_url="http://127.0.0.1:8001", http_post=http)

    result = _run(tool, {"query": "redis 内存溢出", "top_k": 5})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/retrieve")
    assert payload["query"] == "redis 内存溢出"
    assert payload["top_k"] == 5


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------


def test_anomaly_missing_values_returns_error():
    tool = AnomalyDetectTool(http_post=FakeHttp())
    result = _run(tool, {})
    assert result["ok"] is False
    assert "参数错误" in result["error"]


def test_rootcause_missing_nodes_returns_error():
    tool = RootCauseTool(http_post=FakeHttp())
    result = _run(tool, {"top_k": 3})
    assert result["ok"] is False
    assert "nodes" in result["error"]


def test_log_classify_missing_logs_returns_error():
    tool = LogClassifyTool(http_post=FakeHttp())
    result = _run(tool, {})
    assert result["ok"] is False
    assert "logs" in result["error"]


def test_retrieve_missing_query_returns_error():
    tool = CaseRetrieveTool(http_post=FakeHttp())
    result = _run(tool, {})
    assert result["ok"] is False
    assert "query" in result["error"]


# ---------------------------------------------------------------------------
# 服务不可达兜底（不抛异常，返回结构化错误）
# ---------------------------------------------------------------------------


def test_service_unreachable_returns_structured_error():
    http = FakeHttp(error=ConnectionError("connection refused"))
    tool = AnomalyDetectTool(http_post=http)

    result = _run(tool, {"values": [1.0, 2.0]})

    assert result["ok"] is False
    assert result["model_status"] == "unavailable"
    assert "ConnectionError" in result["error"]
    # 不抛异常，Agent 可继续循环


# ---------------------------------------------------------------------------
# 注册与执行集成
# ---------------------------------------------------------------------------


def test_build_tools_returns_nine_low_risk_tools():
    tools = build_nn_perception_tools(base_url="http://127.0.0.1:8001")
    names = {t.name for t in tools}
    assert names == {
        "nn.anomaly", "nn.rootcause", "nn.log_classify", "nn.retrieve",
        "nn.trace", "nn.forecast", "nn.tgat", "nn.vision_forecast",
        "nn.vision_pipeline",
    }
    for t in tools:
        assert t.requires_approval is False  # 全部只读低风险


def test_forecast_payload_and_url():
    from agent.tools.builtin.nn_perception import ForecastTool
    http = FakeHttp({"/api/nn/forecast": {"ok": True, "points": [], "model_status": "fallback"}})
    tool = ForecastTool(base_url="http://127.0.0.1:8001", http_post=http)
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]

    result = _run(tool, {"values": values, "horizon": 4, "upper_threshold": 10.0})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/forecast")
    assert payload["values"] == values
    assert payload["horizon"] == 4
    assert payload["upper_threshold"] == 10.0


def test_forecast_short_series_returns_error():
    from agent.tools.builtin.nn_perception import ForecastTool
    tool = ForecastTool(http_post=FakeHttp())
    result = _run(tool, {"values": [1.0, 2.0]})
    assert result["ok"] is False
    assert "至少 8 个点" in result["error"]


def test_tgat_payload_and_url():
    from agent.tools.builtin.nn_perception import TGATAnalyzeTool
    http = FakeHttp({"/api/nn/tgat": {"ok": True, "root_candidates": [], "spread_path": []}})
    tool = TGATAnalyzeTool(base_url="http://127.0.0.1:8001", http_post=http)
    snaps = [{"timestamp": 100.0, "nodes": [{"alert_id": "redis"}], "edges": []}]

    result = _run(tool, {"snapshots": snaps, "top_k": 3})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/tgat")
    assert payload["snapshots"] == snaps
    assert payload["top_k"] == 3


def test_tgat_missing_snapshots_returns_error():
    from agent.tools.builtin.nn_perception import TGATAnalyzeTool
    tool = TGATAnalyzeTool(http_post=FakeHttp())
    result = _run(tool, {})
    assert result["ok"] is False
    assert "snapshots" in result["error"]


def test_trace_payload_and_url():
    from agent.tools.builtin.nn_perception import TraceAnalyzeTool
    http = FakeHttp({"/api/nn/trace": {"ok": True, "is_anomaly": True, "root_candidates": []}})
    tool = TraceAnalyzeTool(base_url="http://127.0.0.1:8001", http_post=http)
    spans = [{"span_id": "s1", "duration_ms": 1200.0, "status_code": 500}]

    result = _run(tool, {"trace_id": "t-1", "spans": spans})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/trace")
    assert payload["trace_id"] == "t-1"
    assert payload["spans"] == spans


def test_trace_missing_spans_returns_error():
    from agent.tools.builtin.nn_perception import TraceAnalyzeTool
    tool = TraceAnalyzeTool(http_post=FakeHttp())
    result = _run(tool, {"trace_id": "t-1"})
    assert result["ok"] is False
    assert "spans" in result["error"]


def _vision_frames():
    return [
        {"frame_id": "f1", "detections": [
            {"label": "person", "confidence": 0.9, "bbox": [0.1, 0.1, 0.2, 0.3]},
        ]},
        {"frame_id": "f2", "detections": [
            {"label": "person", "confidence": 0.9, "bbox": [0.2, 0.1, 0.3, 0.3]},
        ]},
    ]


def test_vision_forecast_payload_and_url():
    from agent.tools.builtin.nn_perception import VisionForecastTool
    http = FakeHttp({"/api/nn/vision-forecast": {"ok": True, "tracks": [], "events": []}})
    tool = VisionForecastTool(base_url="http://127.0.0.1:8001", http_post=http)
    frames = _vision_frames()
    zones = [{"zone_id": "cabinet", "kind": "danger", "bbox": [0.5, 0.0, 0.9, 0.5]}]

    result = _run(tool, {"frames": frames, "zones": zones, "horizon": 4})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/vision-forecast")
    assert payload["frames"] == frames
    assert payload["zones"] == zones
    assert payload["horizon"] == 4


def test_vision_forecast_requires_two_frames():
    from agent.tools.builtin.nn_perception import VisionForecastTool
    tool = VisionForecastTool(http_post=FakeHttp())
    result = _run(tool, {"frames": _vision_frames()[:1]})
    assert result["ok"] is False
    assert "至少 2 帧" in result["error"]


def test_vision_forecast_requires_detections():
    from agent.tools.builtin.nn_perception import VisionForecastTool
    tool = VisionForecastTool(http_post=FakeHttp())
    frames = [{"frame_id": "f1"}, {"frame_id": "f2"}]
    result = _run(tool, {"frames": frames})
    assert result["ok"] is False
    assert "detections" in result["error"]


def test_vision_pipeline_payload_and_url():
    from agent.tools.builtin.nn_perception import VisionPipelineTool
    http = FakeHttp({"/api/nn/vision-pipeline": {"ok": True, "frames_analyzed": 3}})
    tool = VisionPipelineTool(base_url="http://127.0.0.1:8001", http_post=http)
    source = {"kind": "directory", "path": "D:/frames", "sample_every_ms": 250}

    result = _run(tool, {"source": source, "horizon": 4, "max_frames": 20})

    assert result["ok"] is True
    url, payload = http.calls[0]
    assert url.endswith("/api/nn/vision-pipeline")
    assert payload["source"] == source
    assert payload["horizon"] == 4
    assert payload["max_frames"] == 20


def test_vision_pipeline_rejects_bad_source():
    from agent.tools.builtin.nn_perception import VisionPipelineTool
    tool = VisionPipelineTool(http_post=FakeHttp())

    assert "source" in _run(tool, {})["error"]
    assert "kind" in _run(tool, {"source": {"kind": "webcam", "path": "x"}})["error"]
    assert "path" in _run(tool, {"source": {"kind": "directory", "path": "  "}})["error"]


def test_tools_register_and_execute_via_executor():
    http = FakeHttp({"/api/nn/anomaly": {"ok": True, "results": [], "model_status": "ok"}})
    registry = ToolRegistry()
    for tool in build_nn_perception_tools(base_url="http://127.0.0.1:8001", http_post=http):
        registry.register(tool)

    executor = AgentExecutor(registry, PolicyEngine(), execution_policy=ExecutionPolicy(max_retries=0))
    step = PlanStep(step_id=1, action="检测异常", tool_name="nn.anomaly",
                    arguments={"values": [1.0, 2.0, 3.0]})

    result = executor.execute(step, ExecutionContext("r", "u"))

    assert result.success is True
    assert result.output["ok"] is True
    assert registry.get("nn.anomaly") is not None


def test_base_url_from_env(monkeypatch):
    monkeypatch.setenv("SMARTOPS_AI_SERVICE_URL", "http://ai-svc:9000/")
    tool = AnomalyDetectTool(http_post=FakeHttp())
    assert tool.base_url == "http://ai-svc:9000"  # 末尾斜杠被去掉


# ---------------------------------------------------------------------------
# 端到端：ReAct Planner 驱动真实感知工具完成完整研判循环
# ---------------------------------------------------------------------------


def test_react_drives_real_perception_tools_end_to_end():
    """阶段 1 目标验证：ReAct 主动调 /api/nn/* 感知工具读证据，再给出根因研判。"""
    from agent.planner.react_planner import ReActPlanner
    from agent.sdk.model import ModelProvider, ModelResponse

    class ScriptedProvider(ModelProvider):
        def __init__(self, responses):
            self.responses = list(responses)

        @property
        def name(self):
            return "scripted"

        async def generate(self, prompt, **kwargs):
            return ModelResponse(content=self.responses.pop(0), model="s", provider="s", metadata={})

    http = FakeHttp({
        "/api/nn/anomaly": {"ok": True, "model_status": "ok",
                            "results": [{"metric": "redis_cpu", "peak_score": 0.87}]},
        "/api/nn/rootcause": {"ok": True, "candidates": [{"alert_id": "redis-01", "score": 0.92}]},
    })
    registry = ToolRegistry()
    for tool in build_nn_perception_tools(base_url="http://127.0.0.1:8001", http_post=http):
        registry.register(tool)
    executor = AgentExecutor(registry, PolicyEngine(), execution_policy=ExecutionPolicy(max_retries=0))

    provider = ScriptedProvider([
        "Thought: 先检测 redis_cpu 异常\nAction: nn.anomaly\nAction Input: {\"values\": [1,2,3], \"metric_name\": \"redis_cpu\"}",
        "Thought: 有异常，定位根因\nAction: nn.rootcause\nAction Input: {\"nodes\": [{\"alert_id\": \"redis-01\"}]}",
        "Final Answer: 根因是 redis-01（置信 0.92），建议检查内存。",
    ])
    planner = ReActPlanner(provider, registry, executor)

    result = planner.run("排查 redis 抖动", ExecutionContext("r", "u"))

    assert result.status == "completed"
    assert "redis-01" in result.final_answer
    # 两个感知工具都被真实 HTTP 调用（经 executor 执行闭环）
    called_urls = [url for url, _ in http.calls]
    assert any("/api/nn/anomaly" in u for u in called_urls)
    assert any("/api/nn/rootcause" in u for u in called_urls)
    # 证据进入轨迹 Observation
    assert "0.87" in result.trajectory[0].observation
    assert "0.92" in result.trajectory[1].observation
    assert len(result.plan.steps) == 2  # 两个感知步骤折算成计划
