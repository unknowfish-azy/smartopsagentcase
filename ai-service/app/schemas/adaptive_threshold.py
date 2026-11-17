"""P1-4 自适应阈值 API Schema。

和 P0-1 的区别：
- P0-1 是 AnomalyTransformer 深模型 / IsolationForest，不知道周期性；
- P1-4 是纯规则（STL 分解 + ACF 周期推断），核心价值是把 seasonality 剥掉后再判异常。
- P1-4 **必须有 calibration 段**——没有"正常基线"就无法推断 seasonal profile。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AdaptiveThresholdRequest(BaseModel):
    """一段"校准 + 检测"的时序，服务端自适应地学 seasonal baseline。

    两种传法（二选一）：
    1. calibration + values：显式把历史正常段和待检测段分开（推荐）
    2. values only：服务端自动把前 2/3 当 calibration、后 1/3 当 values

    最小长度要求：calibration ≥ 32 点（ACF 周期推断需要足够样本），
    values ≥ 12 点（太短没意义）。
    """

    calibration: list[float] | None = Field(
        default=None, description="校准段（纯正常），推荐；不传则从 values 切分",
    )
    values: list[float] = Field(
        ..., min_length=12, description="待检测段（可以含故障）",
    )
    metric_name: str | None = Field(default=None, description="指标名，返回里引用")
    k: float = Field(default=3.0, ge=1.5, le=8.0, description="z-score 阈值倍数（和 DetectorConfig.k 对齐）")
    window: int = Field(default=10, ge=5, le=60, description="滚动窗口（供 rolling_z 退化路径）")
    alpha: float = Field(default=0.2, ge=0.05, le=0.8, description="EWMA 平滑系数")
    contamination: float = Field(default=0.05, ge=0.01, le=0.3, description="IsolationForest contamination（退化路径用）")
    force_period: int | None = Field(default=None, ge=2, le=168, description="手动指定周期；不传则 ACF 自动推断")


class DetectorHits(BaseModel):
    """单个自适应检测器的命中情况。"""

    detector: Literal["adaptive_threshold", "seasonal_ewma"]
    binary_mask: list[bool]
    anomaly_count: int
    spans: list[dict[str, int]] = Field(
        default_factory=list,
        description="聚合后的异常 span：[{start, end, point_count}]",
    )


class AdaptiveThresholdResponse(BaseModel):
    """P1-4 自适应阈值检测结果。"""

    ok: bool = True
    mode: Literal["stl", "degraded_rolling", "degraded_ewma"]
    degraded_reason: str | None = None

    # 周期推断
    inferred_period: int | None = Field(description="ACF 自动推断的周期；如果 force_period 传了就是那个值")
    period_source: Literal["acf", "force", "unavailable"]

    # 校准段统计（Agent 可以知道"正常基线长什么样"）
    calibration_mean: float = 0.0
    calibration_std: float = 0.0
    calibration_len: int = 0

    # 自适应基线细节（给前端/Agent 可视化）
    seasonal_profile: list[float] = Field(default_factory=list, description="STL 学到的 seasonal 模板，长度 = period")
    baseline_track: list[float] = Field(default_factory=list, description="检测段的自适应基线（EWMA trend + seasonal）")

    # 两个检测器结果
    adaptive_threshold: DetectorHits
    seasonal_ewma: DetectorHits

    # 附加：退化路径里用的是什么
    fallback_detectors_available: list[str] = Field(default_factory=list)


class AdaptiveThresholdModelInfo(BaseModel):
    """GET /api/nn/adaptive-threshold-info 状态。"""

    available: bool = True
    kind: Literal["stl", "degraded"] = "stl"
    reason: str | None = None
    statsmodels_available: bool = False
    inference_method: str = "acf_autocorrelation"
    note: str = (
        "P1-4 自适应阈值：STL 季节分解 + residual z-score。"
        "解决 '白天高/凌晨低' 导致固定阈值误报漏报的问题。"
    )
