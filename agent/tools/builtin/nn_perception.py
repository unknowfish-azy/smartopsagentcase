"""神经网络感知工具（P2 决策层：把 ai-service 的 /api/nn/* 注册为 Agent 工具）。

定位：这些是 Agent 的「感知器官」，全部是**只读、LOW 风险、SAFE_RETRY 幂等**工具。
ReAct/LLM Planner 在循环里主动调用它们获取结构化证据（异常分 / 根因候选 / 日志分类 /
历史故障案例），**决策权仍在 Agent**——感知工具只给客观打分，不给最终处置结论。

设计要点：
* 走 HTTP 调用独立部署的 ai-service（FastAPI），模型权重与 Agent 代码解耦，
  训练/迭代神经网络不需要改动 Agent 侧任何东西。
* 每个工具对应一个 /api/nn/* 端点，input_schema 与 ai-service 的 pydantic 请求模型对齐，
  让 LLM 能照着 schema 填参；最终参数合法性由 ai-service 的 pydantic 强校验兜底。
* ai-service 不可达 / 模型缺失时**不抛异常中断循环**，而是返回结构化错误
  （ok=False, model_status=unavailable），让 ReAct 把它当 Observation 继续研判或换路。
* HTTP 客户端可注入（_http），便于测试用 fake 替代真实网络。
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable

import httpx

from agent.policies.risk import RiskLevel
from agent.sdk.tool import PluginTool, ToolDefinition

# ai-service 默认地址；可被 SMARTOPS_AI_SERVICE_URL 覆盖
DEFAULT_AI_SERVICE_URL = "http://127.0.0.1:8001"

# 可注入的 async POST： (url, payload) -> dict
HttpPost = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def _default_base_url() -> str:
    return os.getenv("SMARTOPS_AI_SERVICE_URL", DEFAULT_AI_SERVICE_URL).rstrip("/")


class NNPerceptionTool(PluginTool):
    """感知工具基类：统一 HTTP POST、超时、错误兜底。"""

    #: 子类覆盖：ai-service 端点路径，如 "/api/nn/anomaly"
    endpoint: str = ""

    def __init__(
        self,
        definition: ToolDefinition,
        *,
        base_url: str | None = None,
        timeout: float = 15.0,
        http_post: HttpPost | None = None,
    ) -> None:
        self.definition = definition
        self.base_url = (base_url or _default_base_url()).rstrip("/")
        self.timeout = timeout
        self._http_post = http_post

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url + self.endpoint
        if self._http_post is not None:
            return await self._http_post(url, payload)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """子类覆盖：把工具参数转成 ai-service 请求体，并做前置校验。"""
        raise NotImplementedError

    async def execute(self, arguments: dict[str, Any], context) -> dict[str, Any]:
        try:
            payload = self.build_payload(arguments)
        except ValueError as exc:
            # 参数问题：直接返回结构化错误，让 Agent 纠正参数而非中断
            return {"ok": False, "error": f"参数错误：{exc}", "tool": self.name}

        try:
            return await self._post(payload)
        except Exception as exc:  # noqa: BLE001 - 感知服务故障不应中断 Agent 循环
            return {
                "ok": False,
                "model_status": "unavailable",
                "error": f"感知服务调用失败（{self.endpoint}）：{type(exc).__name__}: {exc}",
                "tool": self.name,
            }


# ---------------------------------------------------------------------------
# P0-1 时序异常检测
# ---------------------------------------------------------------------------


class AnomalyDetectTool(NNPerceptionTool):
    """时序异常检测（AnomalyTransformer / IsolationForest fallback）。"""

    endpoint = "/api/nn/anomaly"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.anomaly",
                description=(
                    "时序异常检测：传一段监控指标序列（CPU/内存/QPS/延迟），返回逐点异常分、"
                    "异常时间段、峰值分。用于判断'哪里指标异常、异常程度、从什么时候开始'。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "properties": {
                        "values": {"type": "array", "items": {"type": "number"},
                                   "description": "单指标数值序列，长度≥window(默认64)"},
                        "metrics": {"type": "object",
                                    "description": "多指标字典 key=指标名 value=序列"},
                        "metric_name": {"type": "string", "description": "单指标时的名字"},
                        "window": {"type": "integer", "default": 64},
                        "threshold_quantile": {"type": "number", "default": 0.95},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not arguments.get("values") and not arguments.get("metrics"):
            raise ValueError("必须提供 values（单指标序列）或 metrics（多指标字典）之一")
        payload: dict[str, Any] = {}
        for key in ("values", "metrics", "metric_name", "window", "threshold_quantile", "task_id"):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# ---------------------------------------------------------------------------
# P0-2 根因定位
# ---------------------------------------------------------------------------


class RootCauseTool(NNPerceptionTool):
    """拓扑根因候选排序（GCN/GAT 或 heuristic）。"""

    endpoint = "/api/nn/rootcause"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.rootcause",
                description=(
                    "根因候选排序：传关联告警图（nodes 告警节点 + edges 关联边），"
                    "返回 top-k 候选根因节点及置信分。只给候选，最终根因由 Agent 综合核验。\n"
                    "nodes 每项：{alert_id(必填), severity=P0/P1/P2/P3, metric, server}。\n"
                    "edges 每项（字段名固定）：{alert_a_id, alert_b_id, lift_score, correlation_type}，"
                    "其中 alert_a_id/alert_b_id 必须是 nodes 里出现过的 alert_id；不确定就传空 edges=[]。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["nodes"],
                    "properties": {
                        "nodes": {
                            "type": "array", "description": "告警节点列表（alert_id 必填）",
                            "items": {"type": "object", "required": ["alert_id"],
                                      "properties": {"alert_id": {"type": "string"},
                                                     "severity": {"type": "string"},
                                                     "metric": {"type": "string"},
                                                     "server": {"type": "string"}}},
                        },
                        "edges": {
                            "type": "array", "description": "关联边；不确定字段就传空数组 []",
                            "items": {"type": "object",
                                      "properties": {"alert_a_id": {"type": "string"},
                                                     "alert_b_id": {"type": "string"},
                                                     "lift_score": {"type": "number"},
                                                     "correlation_type": {"type": "string"}}},
                        },
                        "top_k": {"type": "integer", "default": 3},
                        "event_id": {"type": "string"},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        nodes = arguments.get("nodes")
        if not nodes or not isinstance(nodes, list):
            raise ValueError("必须提供非空 nodes（告警节点列表）")
        payload: dict[str, Any] = {"nodes": [_normalize_node(n) for n in nodes if isinstance(n, dict)]}
        edges = arguments.get("edges")
        if isinstance(edges, list):
            payload["edges"] = [_normalize_edge(e) for e in edges if isinstance(e, dict)]
        for key in ("top_k", "event_id", "event_key", "detail"):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# 小模型常把 severity 写成 high/medium/low 或中文，归一化到 schema 要求的 P0-P3，
# 否则 ai-service 的 pydantic 强校验会 422。未知值回退 P2（schema 默认）。
_SEVERITY_MAP = {
    "critical": "P0", "p0": "P0", "致命": "P0", "紧急": "P0",
    "high": "P1", "p1": "P1", "高": "P1", "严重": "P1",
    "medium": "P2", "p2": "P2", "中": "P2", "warning": "P2", "警告": "P2",
    "low": "P3", "p3": "P3", "低": "P3", "info": "P3", "信息": "P3",
}


def _normalize_severity(value: Any) -> str:
    if value is None:
        return "P2"
    return _SEVERITY_MAP.get(str(value).strip().lower(), "P2")


def _normalize_node(node: dict[str, Any]) -> dict[str, Any]:
    out = dict(node)
    if "severity" in out:
        out["severity"] = _normalize_severity(out["severity"])
    return out


def _normalize_edge(edge: dict[str, Any]) -> dict[str, Any]:
    """容忍小模型把边写成 from/to，归一到 alert_a_id/alert_b_id。"""
    out = dict(edge)
    if "alert_a_id" not in out and "from" in out:
        out["alert_a_id"] = out.pop("from")
    if "alert_b_id" not in out and "to" in out:
        out["alert_b_id"] = out.pop("to")
    # type 是 Python 内置风格，schema 用 correlation_type
    if "correlation_type" not in out and "type" in out:
        out.pop("type")  # 自定义 type 值（如 resource_competition）不合法，丢弃走默认
    return out


# ---------------------------------------------------------------------------
# P1-2 日志分类 + 降噪
# ---------------------------------------------------------------------------


class LogClassifyTool(NNPerceptionTool):
    """日志分类与 noise 前置过滤（TinyBERT/TextCNN/heuristic）。"""

    endpoint = "/api/nn/log-classify"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.log_classify",
                description=(
                    "日志分类+降噪：批量日志 → 8 类分类（oom/timeout/disk_full/...）并过滤 noise 心跳。"
                    "告警风暴时先调它，只把非 noise 异常日志送去根因研判，减少噪声与 token。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["logs"],
                    "properties": {
                        "logs": {"type": "array", "description": "日志列表，每项 {text 必填, source?}",
                                 "items": {"type": "object"}},
                        "filter_noise": {"type": "boolean", "default": True},
                        "min_confidence": {"type": "number", "default": 0.3},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        logs = arguments.get("logs")
        if not logs or not isinstance(logs, list):
            raise ValueError("必须提供非空 logs（日志列表，每项含 text）")
        payload: dict[str, Any] = {"logs": logs}
        for key in ("filter_noise", "min_confidence"):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# ---------------------------------------------------------------------------
# P1-3 故障案例向量检索
# ---------------------------------------------------------------------------


class CaseRetrieveTool(NNPerceptionTool):
    """历史故障案例检索（TinyBERT embedding + faiss）。"""

    endpoint = "/api/nn/retrieve"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.retrieve",
                description=(
                    "历史故障案例检索：用自然语言描述当前故障现象，检索相似历史案例"
                    "（根因、处置动作、效果）。用于借鉴历史经验辅助研判。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string", "description": "故障现象描述"},
                        "top_k": {"type": "integer", "default": 3},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments.get("query")
        if not query or not isinstance(query, str):
            raise ValueError("必须提供 query（故障现象描述）")
        payload: dict[str, Any] = {"query": query}
        if arguments.get("top_k") is not None:
            payload["top_k"] = arguments["top_k"]
        return payload


# ---------------------------------------------------------------------------
# P2 阶段 2 调用链 Trace 感知
# ---------------------------------------------------------------------------


class TraceAnalyzeTool(NNPerceptionTool):
    """调用链 Trace 异常感知（TraceFormer / heuristic）。"""

    endpoint = "/api/nn/trace"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.trace",
                description=(
                    "调用链 Trace 异常感知：传一条调用链的 span 序列（SkyWalking/Jaeger），"
                    "返回每 span 异常分、慢节点、错误 span、关键路径、top-k 可疑 span。"
                    "用于分布式追踪维度定位慢/错的调用环节。\n"
                    "spans 每项：{span_id(必填), parent_id, service, operation, "
                    "duration_ms(必填), status_code, is_error}；parent_id 指向父 span，根 span 为 null。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["trace_id", "spans"],
                    "properties": {
                        "trace_id": {"type": "string", "description": "调用链 id"},
                        "spans": {
                            "type": "array", "description": "span 序列（span_id/duration_ms 必填）",
                            "items": {"type": "object", "required": ["span_id", "duration_ms"],
                                      "properties": {"span_id": {"type": "string"},
                                                     "parent_id": {"type": ["string", "null"]},
                                                     "service": {"type": "string"},
                                                     "operation": {"type": "string"},
                                                     "duration_ms": {"type": "number"},
                                                     "status_code": {"type": "integer"},
                                                     "is_error": {"type": "boolean"}}},
                        },
                        "slow_threshold_ms": {"type": "number", "default": 1000.0},
                        "top_k": {"type": "integer", "default": 3},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not arguments.get("trace_id"):
            raise ValueError("必须提供 trace_id")
        spans = arguments.get("spans")
        if not spans or not isinstance(spans, list):
            raise ValueError("必须提供非空 spans（span 序列）")
        payload: dict[str, Any] = {"trace_id": arguments["trace_id"], "spans": spans}
        for key in ("slow_threshold_ms", "error_status_min", "top_k"):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# ---------------------------------------------------------------------------
# P2 阶段 4 时序预测（PatchTST）
# ---------------------------------------------------------------------------


class ForecastTool(NNPerceptionTool):
    """单指标多步预测（PatchTST / linear / seasonal_naive）。"""

    endpoint = "/api/nn/forecast"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.forecast",
                description=(
                    "时序预测：传一段按时间升序的单指标序列，返回未来点值、95% 残差近似区间、"
                    "趋势和启发式风险依据。用于判断指标走势与是否将越过业务上下限；"
                    "risk_score 不是校准概率。至少传 8 个点，可传 horizon、seasonal_period、"
                    "upper_threshold、lower_threshold。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["values"],
                    "properties": {
                        "values": {"type": "array", "minItems": 8,
                                   "items": {"type": "number"}, "description": "单指标历史序列"},
                        "horizon": {"type": "integer", "default": 6, "minimum": 1, "maximum": 64},
                        "metric_name": {"type": "string"},
                        "seasonal_period": {"type": "integer", "default": 0},
                        "upper_threshold": {"type": ["number", "null"]},
                        "lower_threshold": {"type": ["number", "null"]},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        values = arguments.get("values")
        if not values or not isinstance(values, list) or len(values) < 8:
            raise ValueError("必须提供至少 8 个点的 values（单指标历史序列）")
        payload: dict[str, Any] = {"values": values}
        for key in (
            "horizon", "metric_name", "seasonal_period", "upper_threshold", "lower_threshold",
        ):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# ---------------------------------------------------------------------------
# P2 阶段 3 动态拓扑根因感知（TGAT）
# ---------------------------------------------------------------------------


class TGATAnalyzeTool(NNPerceptionTool):
    """动态拓扑根因感知（TGAT / heuristic），面向 K8s 动态扩缩容。"""

    endpoint = "/api/nn/tgat"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.tgat",
                description=(
                    "动态拓扑根因感知：传**多个时间切片的图序列**（拓扑随时间变化），"
                    "输出跨时间聚合的根因候选、异常传播路径 spread_path、拓扑动态变化。"
                    "与 nn.rootcause（静态单快照）互补，面向 K8s 扩缩容、故障沿调用链传播场景。\n"
                    "snapshots 每项：{timestamp(递增), nodes:[{alert_id,severity,status}], "
                    "edges:[{alert_a_id,alert_b_id}]}；severity=P0-P3，status=OPEN/CLOSED。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["snapshots"],
                    "properties": {
                        "snapshots": {
                            "type": "array", "description": "时间切片序列（按 timestamp 升序）",
                            "items": {"type": "object", "required": ["timestamp", "nodes"],
                                      "properties": {"timestamp": {"type": "number"},
                                                     "nodes": {"type": "array"},
                                                     "edges": {"type": "array"}}},
                        },
                        "top_k": {"type": "integer", "default": 3},
                        "time_decay": {"type": "number", "default": 0.9},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        snapshots = arguments.get("snapshots")
        if not snapshots or not isinstance(snapshots, list):
            raise ValueError("必须提供非空 snapshots（时间切片图序列）")
        payload: dict[str, Any] = {"snapshots": snapshots}
        for key in ("top_k", "time_decay"):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# ---------------------------------------------------------------------------
# 巡检视觉事件预测（多目标跟踪 + 轨迹外推 + 区域事件）
# ---------------------------------------------------------------------------


class VisionForecastTool(NNPerceptionTool):
    """巡检视觉事件预测：检测框序列 → 未来轨迹与区域事件。"""

    endpoint = "/api/nn/vision-forecast"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.vision_forecast",
                description=(
                    "巡检视觉事件预测：传**按时间排列的检测框序列**（每帧 detections，"
                    "bbox 为 0..1 归一化 x1,y1,x2,y2），返回多目标轨迹、未来路径、"
                    "区域进入/离开/停留超时事件与 ETA。可选 zones 指定禁入区/关注区"
                    "（kind=danger/inspect/normal）。当前为恒速几何基线，probability "
                    "是启发式打分、未经校准，**不能当作故障概率**；帧数或检测质量不足时"
                    "会标 model_status=degraded。需要检测结果时先用目标检测器产出 bbox。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["frames"],
                    "properties": {
                        "frames": {
                            "type": "array",
                            "description": "帧观测序列，按采集顺序，至少 2 帧",
                            "items": {
                                "type": "object",
                                "required": ["frame_id"],
                                "properties": {
                                    "frame_id": {"type": "string"},
                                    "captured_at_ms": {"type": "number"},
                                    "detections": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "required": ["label", "confidence", "bbox"],
                                            "properties": {
                                                "label": {"type": "string"},
                                                "confidence": {"type": "number"},
                                                "bbox": {"type": "array",
                                                         "items": {"type": "number"}},
                                            },
                                        },
                                    },
                                },
                            },
                        },
                        "zones": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["zone_id", "bbox"],
                                "properties": {
                                    "zone_id": {"type": "string"},
                                    "kind": {"type": "string",
                                             "enum": ["danger", "inspect", "normal"]},
                                    "bbox": {"type": "array", "items": {"type": "number"}},
                                },
                            },
                        },
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "horizon": {"type": "integer", "default": 5},
                        "frame_interval_ms": {"type": "number", "default": 500},
                        "lost_after_frames": {"type": "integer", "default": 2},
                        "dwell_ms": {"type": "number"},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        frames = arguments.get("frames")
        if not isinstance(frames, list) or len(frames) < 2:
            raise ValueError("frames 必须是至少 2 帧的数组")
        if not any((frame or {}).get("detections") for frame in frames):
            raise ValueError("frames 中没有任何 detections，请先运行目标检测器")

        payload: dict[str, Any] = {"frames": frames}
        for key in (
            "zones", "labels", "horizon", "frame_interval_ms",
            "lost_after_frames", "dwell_ms",
        ):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


class VisionPipelineTool(NNPerceptionTool):
    """取帧 → 检测 → 预测：给目录/视频，服务端自动出检测序列与预测。"""

    endpoint = "/api/nn/vision-pipeline"

    def __init__(self, **kwargs) -> None:
        super().__init__(
            ToolDefinition(
                name="nn.vision_pipeline",
                description=(
                    "巡检视觉端到端分析：传一个**服务端可读的图片目录或视频/RTSP 地址**，"
                    "服务端逐帧跑目标检测（torchvision FasterRCNN，BSD-3），再按时间轴"
                    "做多目标跟踪、未来轨迹外推与区域进入/离开事件。\n\n"
                    "口径必须如实转述：目录帧源没有真实采集时间，captured_at_ms 是"
                    "「序号 × sample_every_ms」的假设，响应里标 time_basis=assumed_uniform；"
                    "解码失败的帧进 frames_skipped；无目标/帧数不足返回 ok=false + error_kind。"
                    "返回的 probability 是几何启发式打分、未经校准，**不能当作故障概率**。\n"
                    "若已有检测框序列，直接用 nn.vision_forecast，不必重跑检测。"
                ),
                risk=RiskLevel.LOW,
                target_type="AI_SERVICE",
                idempotency="SAFE_RETRY",
                input_schema={
                    "type": "object",
                    "required": ["source"],
                    "properties": {
                        "source": {
                            "type": "object",
                            "required": ["kind", "path"],
                            "properties": {
                                "kind": {"type": "string", "enum": ["directory", "video"]},
                                "path": {"type": "string",
                                         "description": "服务端本地目录或视频/RTSP 地址"},
                                "sample_every_ms": {"type": "number", "default": 500},
                            },
                        },
                        "detector": {
                            "type": "object",
                            "properties": {
                                "weights_path": {"type": "string"},
                                "class_names": {"type": "array", "items": {"type": "string"}},
                                "score_threshold": {"type": "number", "default": 0.35},
                                "pretrained": {"type": "boolean", "default": True},
                                "num_classes": {"type": "integer"},
                                "device": {"type": "string"},
                            },
                        },
                        "zones": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "required": ["zone_id", "bbox"],
                                "properties": {
                                    "zone_id": {"type": "string"},
                                    "kind": {"type": "string",
                                             "enum": ["danger", "inspect", "normal"]},
                                    "bbox": {"type": "array", "items": {"type": "number"}},
                                },
                            },
                        },
                        "labels": {"type": "array", "items": {"type": "string"}},
                        "horizon": {"type": "integer", "default": 5},
                        "frame_interval_ms": {"type": "number", "default": 500},
                        "lost_after_frames": {"type": "integer", "default": 2},
                        "dwell_ms": {"type": "number"},
                        "max_frames": {"type": "integer", "default": 60},
                    },
                },
            ),
            **kwargs,
        )

    def build_payload(self, arguments: dict[str, Any]) -> dict[str, Any]:
        source = arguments.get("source")
        if not isinstance(source, dict):
            raise ValueError("source 必须是对象，含 kind 与 path")
        if source.get("kind") not in ("directory", "video"):
            raise ValueError("source.kind 只能是 directory 或 video")
        if not str(source.get("path") or "").strip():
            raise ValueError("source.path 不能为空")

        payload: dict[str, Any] = {"source": source}
        for key in (
            "detector", "zones", "labels", "horizon", "frame_interval_ms",
            "lost_after_frames", "dwell_ms", "max_frames",
        ):
            if arguments.get(key) is not None:
                payload[key] = arguments[key]
        return payload


# ---------------------------------------------------------------------------
# 注册入口
# ---------------------------------------------------------------------------


def build_nn_perception_tools(
    *,
    base_url: str | None = None,
    timeout: float = 15.0,
    http_post: HttpPost | None = None,
) -> list[NNPerceptionTool]:
    """构造全部神经网络感知工具，供 build_agent_assembly(tools=...) 一键注册。

        assembly = build_agent_assembly(tools=build_nn_perception_tools())
    """
    kwargs = {"base_url": base_url, "timeout": timeout, "http_post": http_post}
    return [
        AnomalyDetectTool(**kwargs),
        RootCauseTool(**kwargs),
        LogClassifyTool(**kwargs),
        CaseRetrieveTool(**kwargs),
        TraceAnalyzeTool(**kwargs),
        ForecastTool(**kwargs),
        TGATAnalyzeTool(**kwargs),
        VisionForecastTool(**kwargs),
        VisionPipelineTool(**kwargs),
    ]


__all__ = [
    "NNPerceptionTool",
    "AnomalyDetectTool",
    "RootCauseTool",
    "LogClassifyTool",
    "CaseRetrieveTool",
    "TraceAnalyzeTool",
    "ForecastTool",
    "TGATAnalyzeTool",
    "VisionForecastTool",
    "VisionPipelineTool",
    "build_nn_perception_tools",
    "DEFAULT_AI_SERVICE_URL",
]
