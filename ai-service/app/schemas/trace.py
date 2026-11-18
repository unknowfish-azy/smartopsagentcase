"""P2 阶段 2：调用链 Trace 感知（TraceFormer）请求/响应模型。"""

from __future__ import annotations

from typing import Optional, List
from pydantic import BaseModel, Field


class Span(BaseModel):
    """单个调用链 span（兼容 SkyWalking/Jaeger 常见字段）。"""
    span_id: str = Field(description="span 唯一 id")
    parent_id: Optional[str] = Field(default=None, description="父 span id，根 span 为 None")
    service: str = Field(default="", description="服务名，如 gateway/redis/mysql")
    operation: str = Field(default="", description="操作名，如 HTTP GET /api/order")
    duration_ms: float = Field(description="耗时（毫秒）")
    status_code: int = Field(default=200, description="状态码，>=500 视为错误")
    is_error: bool = Field(default=False, description="是否错误 span")
    start_time: Optional[float] = Field(default=None, description="开始时间戳（秒，可选）")


class TraceAnalyzeRequest(BaseModel):
    trace_id: str = Field(description="调用链 id")
    spans: List[Span] = Field(min_length=1, description="span 序列")
    slow_threshold_ms: float = Field(default=1000.0, description="慢 span 阈值（毫秒）")
    error_status_min: int = Field(default=500, description="错误状态码下限")
    top_k: int = Field(default=3, ge=1, le=20, description="返回 top-k 异常 span")


class SpanScore(BaseModel):
    span_id: str
    service: str
    operation: str
    duration_ms: float
    status_code: int
    anomaly_score: float = Field(ge=0.0, le=1.0, description="异常分 0-1")
    is_slow: bool
    is_error: bool
    reason: str = ""


class TraceAnalyzeResponse(BaseModel):
    ok: bool
    mode: str = Field(description="traceformer / heuristic")
    trace_id: str
    anomaly_score: float = Field(description="整条链路异常分 0-1")
    is_anomaly: bool
    span_scores: List[SpanScore]
    slow_spans: List[str] = Field(description="慢 span id 列表")
    error_spans: List[str] = Field(description="错误 span id 列表")
    critical_path: List[str] = Field(description="关键路径（按耗时主导的服务序列）")
    root_candidates: List[SpanScore] = Field(description="top-k 最可疑 span")
    explanation: str = ""
