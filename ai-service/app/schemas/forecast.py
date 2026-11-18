"""PatchTST 时序预测请求/响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat, model_validator


class ForecastRequest(BaseModel):
    values: list[FiniteFloat] = Field(min_length=8, max_length=4096, description="按时间升序的单指标序列")
    horizon: int = Field(default=6, ge=1, le=64, description="未来预测点数")
    metric_name: str = Field(default="unknown", description="指标名")
    seasonal_period: int = Field(default=0, ge=0, le=512, description="可选周期；降级时 >1 使用季节朴素预测")
    upper_threshold: FiniteFloat | None = Field(default=None, description="可选业务上限，用于趋势风险研判")
    lower_threshold: FiniteFloat | None = Field(default=None, description="可选业务下限，用于趋势风险研判")

    @model_validator(mode="after")
    def validate_thresholds(self):
        if self.upper_threshold is not None and self.lower_threshold is not None:
            if self.upper_threshold <= self.lower_threshold:
                raise ValueError("upper_threshold 必须大于 lower_threshold")
        return self


class ForecastPoint(BaseModel):
    step: int = Field(ge=1, description="相对最后一个观测点的未来步数")
    value: float
    lower: float = Field(description="95% 残差近似区间下界")
    upper: float = Field(description="95% 残差近似区间上界")


class ForecastResponse(BaseModel):
    ok: bool = True
    mode: Literal["patchtst", "linear", "seasonal_naive"]
    model_status: Literal["ok", "fallback"]
    model_status_detail: str | None = None
    metric_name: str
    horizon: int
    points: list[ForecastPoint]
    trend: Literal["rising", "falling", "stable"]
    trend_slope: float = Field(description="每个采样间隔的变化量")
    risk_score: float = Field(ge=0.0, le=1.0, description="启发式趋势风险分，不是校准概率")
    risk_level: Literal["low", "medium", "high"]
    risk_basis: list[str]
    interval_level: float = 0.95
    interval_method: str = "gaussian_residual_approximation"
    explanation: str


class ForecastModelInfo(BaseModel):
    available: bool
    kind: Literal["patchtst", "fallback", "unavailable"]
    reason: str | None = None
    torch_available: bool = False
    context_length: int | None = None
    horizon: int | None = None
    normalization: dict | None = None
