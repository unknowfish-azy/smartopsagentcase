"""取帧 → 检测 → 预测 的端到端请求/响应模型。

与 `vision_forecast.py` 的分工：那边只收归一化检测框，调用方得自己准备好
`frames[].detections`；这里把"给一个目录/视频，自动出检测序列与预测"补齐。

口径约定：
* `source.sample_every_ms` 是**时间假设**，不是读取图片元数据得到的采集时间；
* 失败一律 `ok=false` + `error_kind`，不返回空轨迹冒充"画面正常"；
* 检测框沿用 0..1 归一化 (x1, y1, x2, y2)。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat, field_validator

from .vision_forecast import VisionForecastResponse, ZoneSpec


class FrameSourceSpec(BaseModel):
    kind: Literal["directory", "video"] = Field(
        default="directory",
        description="directory=本地图片目录；video=视频文件或 RTSP/HTTP 流（需要 opencv）",
    )
    path: str = Field(min_length=1, max_length=1024, description="目录路径或视频地址")
    sample_every_ms: FiniteFloat | None = Field(
        default=None,
        gt=0.0,
        le=60_000.0,
        description="目录帧源：相邻帧的时间步长假设（默认 500ms）；视频帧源：最小抽帧间隔",
    )

    @field_validator("path")
    @classmethod
    def strip_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("path 不能为空白")
        return value


class DetectorSpec(BaseModel):
    weights_path: str | None = Field(
        default=None,
        max_length=1024,
        description="train_vision_frcnn.py 产出的 model.pt；为 None 时按 pretrained 决定",
    )
    class_names: list[str] = Field(default_factory=list, max_length=64)
    score_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    pretrained: bool = Field(
        default=True,
        description="无权重时是否加载 COCO 预训练头（首次会联网下载，离线环境请置 false 并提供权重）",
    )
    num_classes: int | None = Field(default=None, ge=2, le=4096)
    device: str | None = Field(default=None, max_length=32)


class VisionPipelineRequest(BaseModel):
    source: FrameSourceSpec
    detector: DetectorSpec = Field(default_factory=DetectorSpec)
    zones: list[ZoneSpec] = Field(default_factory=list, max_length=32)
    labels: list[str] = Field(default_factory=list, max_length=32, description="只保留这些类别；为空表示全部")
    horizon: int = Field(default=5, ge=1, le=30)
    frame_interval_ms: FiniteFloat = Field(default=500.0, gt=0.0, le=60_000.0)
    lost_after_frames: int = Field(default=2, ge=0, le=20)
    dwell_ms: FiniteFloat | None = Field(default=None, gt=0.0)
    max_frames: int = Field(default=60, ge=2, le=600, description="最多读多少帧（防止长视频打爆内存）")


class VisionPipelineResponse(BaseModel):
    ok: bool
    schema_version: str = "smartops.vision_pipeline.v1"
    error: str | None = None
    error_kind: str | None = Field(
        default=None,
        description="NO_FRAMES / TOO_FEW_FRAMES / NO_DETECTIONS / FrameSourceUnavailable / DetectorUnavailable",
    )
    source: dict = Field(default_factory=dict)
    detector: dict = Field(default_factory=dict)
    frames_analyzed: int = 0
    frames_skipped: list[dict] = Field(default_factory=list, description="解码失败的帧与原因")
    detections_per_frame: list[int] = Field(default_factory=list)
    total_detections: int = 0
    filtered_by_label: int = 0
    invalid_detections: int = 0
    truncated: bool = Field(default=False, description="达到 max_frames 上限，源里可能还有未读帧")
    forecast: VisionForecastResponse | None = None
