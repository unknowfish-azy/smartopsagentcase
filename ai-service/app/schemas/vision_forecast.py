"""巡检视觉事件预测的请求/响应模型。

口径约定（与 existing forecast schema 保持一致）：
* 概率字段一律是**启发式打分**，不是校准后的故障概率；
* 空数据返回 NO_DATA 语义（tracks/events 为空 + 降级原因），绝不补 0 冒充正常；
* bbox 统一为 0..1 归一化的 (x1, y1, x2, y2)，与 vision/grounding.py 的坐标口径对齐。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat, model_validator


def _check_box(box: list[float]) -> list[float]:
    x1, y1, x2, y2 = box
    if not (0.0 <= x1 < x2 <= 1.0 and 0.0 <= y1 < y2 <= 1.0):
        raise ValueError("bbox 必须是 0..1 归一化坐标，且满足 x1<x2、y1<y2")
    return box


class Detection(BaseModel):
    label: str = Field(min_length=1, max_length=64, description="类别名，如 person / smoke / cabinet_door")
    confidence: FiniteFloat = Field(ge=0.0, le=1.0)
    bbox: list[FiniteFloat] = Field(min_length=4, max_length=4, description="归一化 x1,y1,x2,y2")

    @model_validator(mode="after")
    def validate_bbox(self):
        _check_box(self.bbox)
        return self


class FrameObservation(BaseModel):
    frame_id: str = Field(min_length=1, max_length=128, description="帧 ID，通常取 robot_frame.id 或时间戳")
    captured_at_ms: FiniteFloat | None = Field(
        default=None,
        description="采集时间（毫秒）。全部帧都提供时按真实间隔计算速度；否则用 frame_interval_ms",
    )
    detections: list[Detection] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def dedupe_frame_id(self):
        if not self.frame_id.strip():
            raise ValueError("frame_id 不能为空白")
        return self


class ZoneSpec(BaseModel):
    zone_id: str = Field(min_length=1, max_length=64)
    kind: Literal["danger", "inspect", "normal"] = Field(
        default="inspect",
        description="danger=禁止进入区域；inspect=关注区域；normal=仅记录不触发事件",
    )
    bbox: list[FiniteFloat] = Field(min_length=4, max_length=4, description="归一化 x1,y1,x2,y2")

    @model_validator(mode="after")
    def validate_bbox(self):
        _check_box(self.bbox)
        return self


class VisionForecastRequest(BaseModel):
    frames: list[FrameObservation] = Field(min_length=2, max_length=600, description="按采集顺序排列的帧观测")
    zones: list[ZoneSpec] = Field(default_factory=list, max_length=32)
    labels: list[str] = Field(default_factory=list, max_length=32, description="只跟踪这些类别；为空表示全部")
    horizon: int = Field(default=5, ge=1, le=30, description="未来预测步数")
    frame_interval_ms: FiniteFloat = Field(
        default=500.0, gt=0.0, le=60_000.0, description="无采集时间时使用的帧间隔",
    )
    lost_after_frames: int = Field(default=2, ge=0, le=20, description="连续缺失多少帧判定目标丢失")
    dwell_ms: FiniteFloat | None = Field(default=None, gt=0.0, description="可选：区域停留超时阈值")

    @model_validator(mode="after")
    def validate_frames(self):
        if not any(frame.detections for frame in self.frames):
            raise ValueError("frames 中没有任何检测结果，无法预测；请检查检测器或筛选条件")
        if self.frames[0].captured_at_ms is not None:
            stamps = [frame.captured_at_ms for frame in self.frames]
            if any(stamp is None for stamp in stamps):
                raise ValueError("captured_at_ms 必须全提供或全省略，不能混用")
        return self


class TrackPoint(BaseModel):
    step: int = Field(ge=1)
    t_ms: float = Field(description="相对最后一帧的时间偏移")
    cx: float
    cy: float
    radius: float = Field(description="位置不确定半径（归一化），随步数增长")


class TrackForecast(BaseModel):
    track_id: str
    label: str
    status: Literal["confirmed", "tentative", "lost"]
    hits: int = Field(description="该轨迹被观测到的帧数")
    missing_frames: int
    last_bbox: list[float]
    velocity: list[float] = Field(description="(vx, vy)，单位：归一化坐标/秒")
    speed: float = Field(description="归一化坐标/秒")
    predicted_path: list[TrackPoint]


class ZoneEvent(BaseModel):
    track_id: str
    label: str
    zone_id: str
    zone_kind: Literal["danger", "inspect", "normal"]
    event: Literal["predicted_enter", "predicted_exit", "dwell_exceeded"]
    step: int | None = Field(default=None, description="predicted_* 的触发步数；dwell 为 null")
    eta_ms: float | None = Field(default=None, description="预计发生时间；dwell 为 0")
    probability: float = Field(ge=0.0, le=1.0, description="几何启发式打分，未经概率校准")
    basis: list[str]


class VisionForecastResponse(BaseModel):
    ok: bool = True
    mode: Literal["geometric"] = "geometric"
    model_status: Literal["geometry_only", "degraded"]
    model_status_detail: str | None = None
    frame_count: int
    dt_ms: float
    tracks: list[TrackForecast]
    events: list[ZoneEvent]
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_level: Literal["low", "medium", "high"]
    risk_basis: list[str]
    data_quality: dict
    explanation: str


class VisionForecastModelInfo(BaseModel):
    available: bool
    kind: Literal["geometric", "learned", "unavailable"]
    learned_backend: list[str] = Field(default_factory=list)
    reason: str | None = None
    supports: list[str] = Field(default_factory=list)
    probability_calibrated: bool = False
    min_frames: int = 2
    max_horizon: int = 30


class VisionFeedbackRequest(BaseModel):
    track_id: str = Field(min_length=1, max_length=64)
    event: Literal["predicted_enter", "predicted_exit", "dwell_exceeded"]
    zone_id: str | None = Field(default=None, max_length=64)
    predicted: bool
    observed: bool
    frame_id: str | None = Field(default=None, max_length=128)
    model_version: str = Field(default="geometry-v1", max_length=64)
    notes: str | None = Field(default=None, max_length=512)


class VisionFeedbackResponse(BaseModel):
    ok: bool = True
    stored: str
    schema_version: str = "smartops.vision_feedback.v1"
