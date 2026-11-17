"""P2-2 故障仿真生成 API Schema。

Agent 给一个故障类别 → 生成一段带校准段的合成时序 → 返回 values + labels + 检测器验证。
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

VALID_CATEGORIES = Literal[
    "oom", "timeout", "disk_full", "connection_refused",
    "process_crash", "auth_error", "network_error",
]
VALID_METRICS = Literal[
    "cpu", "memory", "disk_usage", "inode_usage",
    "network_rx", "network_tx", "latency",
    "http_401", "http_403", "packet_loss",
]


class SimulateRequest(BaseModel):
    """请求一段合成故障时序。"""

    category: VALID_CATEGORIES = Field(..., description="故障类别，决定故障形状模板")
    metric: VALID_METRICS | None = Field(
        default=None, description="指定指标名；不传则按 category 默认模板自动选",
    )
    seed: int = Field(default=42, description="随机种子，确保可复现")
    severity: float = Field(default=1.0, ge=0.3, le=2.0, description="故障严重度，缩放峰值（0.3~2.0）")
    calibration_len: int = Field(default=96, ge=24, le=1000, description="校准段长度（正常基线）")
    test_len: int = Field(default=48, ge=12, le=500, description="测试段长度（含故障注入）")
    inject_start: int | None = Field(default=None, description="故障注入起点（test 段内），不传则自动选 1/3 位置")
    add_seasonality: bool = Field(default=True, description="是否加昼夜/周期季节项")
    add_noise: bool = Field(default=True, description="是否加高斯噪声")
    verify: bool = Field(default=True, description="是否用 detect_all() 跑检测器验证")


class DetectorVerification(BaseModel):
    """单个检测器的命中情况。"""

    precision: float
    recall: float
    f1: float
    hit: bool


class DetectorVerificationBlock(BaseModel):
    """detect_all() 验证块。"""

    available: bool
    per_detector: dict[str, DetectorVerification] = Field(default_factory=dict)
    expected_hit: list[str] = Field(default_factory=list)
    coverage: float = 0.0


class SimulateResponse(BaseModel):
    """合成故障时序响应。"""

    ok: bool = True
    mode: Literal["rule_based"] = "rule_based"
    category: str
    metric: str
    calibration: list[float]
    values: list[float]
    labels: list[bool]
    meta: dict[str, Any]
    detector_verification: DetectorVerificationBlock


class SimulatorModelInfo(BaseModel):
    """模拟器状态。纯 numpy 规则实现，永远 available。"""

    available: bool = True
    kind: Literal["rule_based"] = "rule_based"
    reason: str | None = None
    categories: list[str] = Field(description="支持的故障类别")
    metrics_per_category: dict[str, list[str]] = Field(description="每个 category 对应的可用指标")
