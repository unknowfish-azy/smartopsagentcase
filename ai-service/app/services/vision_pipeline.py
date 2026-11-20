"""取帧 → 检测 → 预测 的端到端适配器。

为什么需要这一层：`vision_forecast` 只消费归一化检测框序列，`vision/detector`
只出单帧框，两者之间缺"把一段真实帧源变成带时间戳的检测序列"的接线。本模块补：

    目录图片 / 视频 / RTSP ──► 逐帧 detect ──► FrameObservation[] ──► forecast()

三条口径：
1. **时间戳是假设，不是元数据**：目录帧源拿不到真实采集时间，用
   `index × sample_every_ms` 均匀外推，`describe()` 里标 `time_basis=assumed_uniform`；
   只有视频源用视频自带 FPS。
2. **读不了的帧要记账**：解码失败进 `frames_skipped` 并带原因，不静默丢帧。
3. **没有目标就不预测**：返回 `ok=false` + `error_kind`，不返回空轨迹冒充"画面正常"。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

from pydantic import ValidationError

from ..schemas.vision_forecast import (
    Detection as DetectionSchema,
    FrameObservation,
    VisionForecastRequest,
)
from ..vision.dataset import IMAGE_SUFFIXES
from ..vision.detector import DetectorUnavailable, TorchvisionDetector
from . import vision_forecast


class FrameSourceUnavailable(RuntimeError):
    """帧源不可用（目录不存在 / 缺 OpenCV / 视频打不开）。消息里必须带原因。"""


@dataclass(frozen=True)
class Frame:
    frame_id: str
    captured_at_ms: float
    image: Any | None
    error: str | None = None


# ---------------------------------------------------------------------------
# 帧源
# ---------------------------------------------------------------------------


def _read_image(path: Path) -> Any:
    """Pillow 解码成 RGB uint8 ndarray；Pillow 只在真正读图时才导入。"""
    try:
        from PIL import Image
    except ImportError as error:  # pragma: no cover - 环境缺依赖
        raise FrameSourceUnavailable("缺少 Pillow，无法解码图片") from error

    import numpy as np

    with Image.open(path) as image:
        # 用 np.array 而不是 np.asarray：PIL 返回只读缓冲，转给 torch 会触发
        # "non-writable tensor" 警告；这里显式拷贝一份可写数组。
        return np.array(image.convert("RGB"))


class DirectoryFrameSource:
    """按文件名排序读取目录里的图片。文件名顺序即时间顺序，这是显式假设。"""

    kind = "directory"

    def __init__(self, path: Path | str, *, sample_every_ms: float = 500.0) -> None:
        self.path = Path(path)
        if not self.path.is_dir():
            raise FrameSourceUnavailable(f"目录不存在：{self.path}")
        self.sample_every_ms = float(sample_every_ms)

    def list_images(self) -> list[Path]:
        return sorted(
            (
                item
                for item in self.path.iterdir()
                if item.is_file() and item.suffix.lower() in IMAGE_SUFFIXES
            ),
            key=lambda item: item.name,
        )

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "frames_total": len(self.list_images()),
            "sample_every_ms": self.sample_every_ms,
            "time_basis": "assumed_uniform",
            "note": "目录帧源没有真实采集时间，captured_at_ms = 序号 × sample_every_ms",
        }

    def frames(self) -> Iterator[Frame]:
        for index, path in enumerate(self.list_images()):
            captured_at_ms = index * self.sample_every_ms
            try:
                image = _read_image(path)
            except Exception as error:  # 单帧坏掉不该拖垮整段
                yield Frame(
                    frame_id=path.stem,
                    captured_at_ms=captured_at_ms,
                    image=None,
                    error=f"解码失败：{error}",
                )
                continue
            yield Frame(frame_id=path.stem, captured_at_ms=captured_at_ms, image=image)


class VideoFrameSource:
    """视频文件或 RTSP/HTTP 流，经 OpenCV 逐帧读取（懒导入，缺失时显式降级）。"""

    kind = "video"

    def __init__(self, path: Path | str, *, sample_every_ms: float | None = None) -> None:
        self.address = str(path)
        self.path = Path(path)
        self.sample_every_ms = float(sample_every_ms) if sample_every_ms else None
        is_stream = "://" in self.address
        if not is_stream and not self.path.is_file():
            raise FrameSourceUnavailable(f"视频文件不存在：{self.path}")

    def describe(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.address,
            "sample_every_ms": self.sample_every_ms,
            "time_basis": "video_fps",
        }

    def frames(self) -> Iterator[Frame]:
        try:
            import cv2
        except ImportError as error:
            raise FrameSourceUnavailable("缺少 opencv-python，无法读取视频/RTSP") from error

        capture = cv2.VideoCapture(self.address)
        if not capture.isOpened():
            capture.release()
            raise FrameSourceUnavailable(f"视频源无法打开：{self.address}")

        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            base_interval = 1000.0 / fps if fps > 0 else 500.0
            step_ms = max(base_interval, self.sample_every_ms or 0.0)

            index = 0
            kept = 0
            next_keep_ms = 0.0
            while True:
                ok, bgr = capture.read()
                if not ok:
                    break
                captured_at_ms = index * base_interval
                index += 1
                if captured_at_ms + 1e-6 < next_keep_ms:
                    continue
                next_keep_ms = captured_at_ms + step_ms
                yield Frame(
                    frame_id=f"{self.path.stem}#{kept:04d}",
                    captured_at_ms=captured_at_ms,
                    image=cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB),
                )
                kept += 1
        finally:
            capture.release()


def build_source(spec: Any) -> DirectoryFrameSource | VideoFrameSource:
    if spec.kind == "video":
        return VideoFrameSource(spec.path, sample_every_ms=spec.sample_every_ms)
    return DirectoryFrameSource(spec.path, sample_every_ms=spec.sample_every_ms or 500.0)


def build_detector(spec: Any) -> TorchvisionDetector:
    return TorchvisionDetector(
        weights_path=spec.weights_path,
        class_names=spec.class_names or None,
        score_threshold=spec.score_threshold,
        device=spec.device,
        pretrained=spec.pretrained,
        num_classes=spec.num_classes,
    )


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def _failure(base: dict[str, Any], error: str, kind: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": error,
        "error_kind": kind,
        "forecast": None,
        "schema_version": "smartops.vision_pipeline.v1",
        **base,
    }


def analyze(
    source: Any,
    detector: Any,
    *,
    zones: Sequence[Any] = (),
    labels: Sequence[str] = (),
    horizon: int = 5,
    frame_interval_ms: float = 500.0,
    lost_after_frames: int = 2,
    dwell_ms: float | None = None,
    max_frames: int = 60,
) -> dict[str, Any]:
    """逐帧检测 → 组装 FrameObservation → 调 `vision_forecast.forecast`。

    `detector` 只需有 `detect(image)`，返回带 `label / confidence / bbox` 的对象，
    因此测试可以注入 fake，不必装 torch。
    """
    label_set = {str(label) for label in labels if str(label)}
    observations: list[FrameObservation] = []
    skipped: list[dict[str, Any]] = []
    per_frame: list[int] = []
    filtered = 0
    invalid = 0
    produced = 0
    truncated = True  # 默认视为被上限截断；读到源末尾才置 False

    for frame in source.frames():
        if produced >= max_frames:
            break
        produced += 1

        if frame.image is None:
            skipped.append({"frame_id": frame.frame_id, "reason": frame.error or "解码失败"})
            continue

        kept: list[DetectionSchema] = []
        for item in detector.detect(frame.image):
            label = str(getattr(item, "label", "") or "")
            if not label:
                invalid += 1
                continue
            if label_set and label not in label_set:
                filtered += 1
                continue
            try:
                kept.append(
                    DetectionSchema(
                        label=label,
                        confidence=float(item.confidence),
                        bbox=[float(value) for value in item.bbox],
                    )
                )
            except (TypeError, ValueError, ValidationError):
                # 框非法（越界/退化）不进轨迹，但计数留证
                invalid += 1

        observations.append(
            FrameObservation(
                frame_id=frame.frame_id,
                captured_at_ms=frame.captured_at_ms,
                detections=kept,
            )
        )
        per_frame.append(len(kept))
    else:
        truncated = False

    describe = getattr(source, "describe", None)
    info = getattr(detector, "info", None)
    base: dict[str, Any] = {
        "source": describe() if callable(describe) else {"kind": getattr(source, "kind", "unknown")},
        "detector": info() if callable(info) else {},
        "frames_analyzed": len(observations),
        "frames_skipped": skipped,
        "detections_per_frame": per_frame,
        "total_detections": sum(per_frame),
        "filtered_by_label": filtered,
        "invalid_detections": invalid,
        "truncated": truncated,
    }

    if not observations:
        return _failure(base, "未读到任何可用帧（目录为空或全部解码失败）", "NO_FRAMES")
    if len(observations) < 2:
        return _failure(
            base,
            f"可用帧 {len(observations)} 少于 2，无法做帧间速度拟合",
            "TOO_FEW_FRAMES",
        )
    if base["total_detections"] == 0:
        return _failure(
            base,
            "未检测到任何目标（检查 score_threshold、类别过滤或画面内容）",
            "NO_DETECTIONS",
        )

    request = VisionForecastRequest(
        frames=observations,
        zones=list(zones),
        labels=list(labels),
        horizon=horizon,
        frame_interval_ms=frame_interval_ms,
        lost_after_frames=lost_after_frames,
        dwell_ms=dwell_ms,
    )
    return {
        "ok": True,
        "error": None,
        "error_kind": None,
        "forecast": vision_forecast.forecast(request),
        "schema_version": "smartops.vision_pipeline.v1",
        **base,
    }


def run(request: Any) -> dict[str, Any]:
    """API 入口：按请求构建帧源与检测器，失败转结构化错误而不是 500。"""
    source = None
    detector = None
    try:
        source = build_source(request.source)
        detector = build_detector(request.detector)
        return analyze(
            source,
            detector,
            zones=request.zones,
            labels=request.labels,
            horizon=request.horizon,
            frame_interval_ms=request.frame_interval_ms,
            lost_after_frames=request.lost_after_frames,
            dwell_ms=request.dwell_ms,
            max_frames=request.max_frames,
        )
    except (FrameSourceUnavailable, DetectorUnavailable) as error:
        context: dict[str, Any] = {}
        if source is not None:
            context["source"] = source.describe()
        if detector is not None:
            context["detector"] = detector.info()
        return _failure(context, str(error), error.__class__.__name__)
