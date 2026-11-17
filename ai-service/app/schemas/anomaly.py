"""P0-1 时序异常检测 API 的 Schema。

Agent 通过 tool 调用 /api/nn/anomaly，传一段指标序列，返回：
- 模型状态（OK / fallback 原因）
- 逐点异常分
- 异常点位置 + 时间段（方便 Agent 研判"从什么时候开始不对"）
- 可选的根因指标提示（如果给了多 metric 的拼接序列）
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AnomalyRequest(BaseModel):
    """一段时序指标，由前端或 Agent tool 调用。

    两种传法：
    1. values: 单 metric 的纯数值序列（最常见，Agent 拉 Prometheus 后直接塞进来）
    2. metrics: 多 metric 的字典（key=metric_name, value=values），服务端会逐 metric 独立评测
    """

    values: list[float] | None = Field(
        default=None, description="单 metric 序列，长度 ≥ window（默认 64）",
    )
    metrics: dict[str, list[float]] | None = Field(
        default=None, description="多 metric 字典，key=metric 名，value=序列",
    )
    window: int = Field(default=64, ge=16, le=1024, description="滑动窗口大小")
    metric_name: str | None = Field(default=None, description="单 metric 时的名字，方便返回里引用")
    task_id: str | None = Field(default=None, description="可选：采集任务 ID，便于 trace")
    threshold_quantile: float = Field(default=0.95, ge=0.5, le=0.999, description="异常分阈值分位")


class AnomalyPoint(BaseModel):
    """一个异常点。"""

    index: int
    score: float
    metric: str | None = None


class AnomalySpan(BaseModel):
    """异常连续时间段（聚合相邻/重叠的异常点，避免 Agent 拿到碎片）。"""

    start: int
    end: int
    point_count: int
    avg_score: float


class MetricAnomalyResult(BaseModel):
    """单 metric 的检测结果。"""

    metric: str
    points: list[AnomalyPoint]
    spans: list[AnomalySpan]
    anomaly_count: int
    span_count: int
    mean_score: float
    peak_score: float
    kind: Literal["anomaly_transformer", "isolation_forest_fallback"]


class AnomalyResponse(BaseModel):
    """统一响应，支持多 metric。"""

    ok: bool = True
    mode: Literal["single", "multi"]
    model_status: Literal["ok", "fallback", "unavailable"]
    model_status_detail: str | None = None
    window: int
    threshold_quantile: float
    results: list[MetricAnomalyResult]
    task_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict, description="预留字段：后端 debug 信息")


class AnomalyModelInfo(BaseModel):
    """GET /api/nn/model-info —— 告诉调用方当前服务端挂的是什么模型。"""

    available: bool
    kind: Literal["anomaly_transformer", "isolation_forest_fallback", "unavailable"]
    reason: str | None = None
    torch_available: bool = False
    window: int | None = None
    latent_dim: int | None = None
