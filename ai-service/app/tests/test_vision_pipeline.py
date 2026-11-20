"""取帧 → 检测 → 预测 适配器的测试。

分三层：
1. 帧源（目录排序/时间戳假设/视频缺失降级）——不依赖 torch、不依赖 cv2；
2. 编排（fake detector 注入）：帧组装、标签过滤、非法框计数、失败语义；
3. 路由：断言 FastAPI 层能拿到结构化响应（torch 不可用时跳过）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.schemas.vision_forecast import ZoneSpec
from app.schemas.vision_pipeline import VisionPipelineRequest
from app.services.vision_pipeline import (
    DirectoryFrameSource,
    FrameSourceUnavailable,
    VideoFrameSource,
    analyze,
    run,
)
from app.vision.detector import Detection, TorchvisionDetector, runtime_status


class FakeDetector:
    """按调用顺序吐出预设检测结果，不加载任何模型。"""

    def __init__(self, outputs: list[list[Detection]]) -> None:
        self.outputs = outputs
        self.calls = 0

    def detect(self, image) -> list[Detection]:
        result = self.outputs[self.calls]
        self.calls += 1
        return result


def _write_images(directory: Path, count: int) -> None:
    from PIL import Image

    for index in range(count):
        array = np.full((16, 16, 3), index * 40, dtype=np.uint8)
        Image.fromarray(array).save(directory / f"frame_{index:03d}.png")


def _moving_person(count: int, start: float = 0.10, step: float = 0.05) -> list[list[Detection]]:
    outputs = []
    for index in range(count):
        x1 = start + index * step
        outputs.append([Detection("person", 0.9, (x1, 0.40, x1 + 0.10, 0.60))])
    return outputs


# ---------------------------------------------------------------------------
# 帧源
# ---------------------------------------------------------------------------


def test_directory_source_sorted_with_assumed_timestamps(tmp_path: Path):
    _write_images(tmp_path, 3)
    source = DirectoryFrameSource(tmp_path, sample_every_ms=250)

    frames = list(source.frames())

    assert [frame.frame_id for frame in frames] == ["frame_000", "frame_001", "frame_002"]
    assert [frame.captured_at_ms for frame in frames] == [0.0, 250.0, 500.0]
    assert source.describe()["time_basis"] == "assumed_uniform"


def test_directory_source_missing_dir_raises(tmp_path: Path):
    with pytest.raises(FrameSourceUnavailable, match="目录不存在"):
        DirectoryFrameSource(tmp_path / "nope")


def test_video_source_missing_file_raises(tmp_path: Path):
    with pytest.raises(FrameSourceUnavailable, match="视频文件不存在"):
        VideoFrameSource(tmp_path / "nope.mp4")


# ---------------------------------------------------------------------------
# 编排
# ---------------------------------------------------------------------------


def test_analyze_builds_forecast_from_detections(tmp_path: Path):
    _write_images(tmp_path, 3)
    detector = FakeDetector(_moving_person(3))

    result = analyze(DirectoryFrameSource(tmp_path), detector)

    assert result["ok"] is True
    assert result["frames_analyzed"] == 3
    assert result["detections_per_frame"] == [1, 1, 1]
    assert result["total_detections"] == 3
    assert result["truncated"] is False

    forecast = result["forecast"]
    assert forecast["frame_count"] == 3
    assert forecast["dt_ms"] == 500.0
    assert len(forecast["tracks"]) == 1
    track = forecast["tracks"][0]
    assert track["label"] == "person"
    assert track["status"] == "confirmed"
    assert track["velocity"][0] > 0  # 向右移动，vx 为正


def test_analyze_emits_zone_event(tmp_path: Path):
    _write_images(tmp_path, 3)
    zone = ZoneSpec(zone_id="door", kind="danger", bbox=[0.40, 0.0, 1.0, 1.0])

    result = analyze(
        DirectoryFrameSource(tmp_path),
        FakeDetector(_moving_person(3)),
        zones=[zone],
        horizon=5,
    )

    events = result["forecast"]["events"]
    assert any(event["event"] == "predicted_enter" and event["zone_id"] == "door" for event in events)
    assert any(event["probability"] <= 0.95 for event in events)  # 启发式打分上限


def test_analyze_filters_labels_and_counts_invalid_boxes(tmp_path: Path):
    _write_images(tmp_path, 2)
    outputs = [
        [
            Detection("person", 0.9, (0.10, 0.10, 0.20, 0.20)),
            Detection("cat", 0.9, (0.30, 0.30, 0.40, 0.40)),
            Detection("person", 0.9, (0.50, 0.50, 0.50, 0.50)),  # 零面积 → 非法
        ],
        [Detection("person", 0.9, (0.12, 0.10, 0.22, 0.20))],
    ]

    result = analyze(DirectoryFrameSource(tmp_path), FakeDetector(outputs), labels=["person"])

    assert result["ok"] is True
    assert result["filtered_by_label"] == 1
    assert result["invalid_detections"] == 1
    assert result["detections_per_frame"] == [1, 1]
    assert {track["label"] for track in result["forecast"]["tracks"]} == {"person"}


def test_analyze_reports_skipped_frames(tmp_path: Path):
    _write_images(tmp_path, 2)
    (tmp_path / "bad.png").write_bytes(b"not-a-png")

    result = analyze(DirectoryFrameSource(tmp_path), FakeDetector(_moving_person(2)))

    assert result["ok"] is True
    assert result["frames_analyzed"] == 2
    assert len(result["frames_skipped"]) == 1
    assert result["frames_skipped"][0]["frame_id"] == "bad"
    assert "解码失败" in result["frames_skipped"][0]["reason"]


def test_analyze_truncates_at_max_frames(tmp_path: Path):
    _write_images(tmp_path, 3)

    result = analyze(DirectoryFrameSource(tmp_path), FakeDetector(_moving_person(2)), max_frames=2)

    assert result["ok"] is True
    assert result["frames_analyzed"] == 2
    assert result["truncated"] is True


def test_analyze_no_detections_is_structured_failure(tmp_path: Path):
    _write_images(tmp_path, 2)

    result = analyze(DirectoryFrameSource(tmp_path), FakeDetector([[], []]))

    assert result["ok"] is False
    assert result["error_kind"] == "NO_DETECTIONS"
    assert result["forecast"] is None


def test_analyze_too_few_frames(tmp_path: Path):
    _write_images(tmp_path, 1)

    result = analyze(DirectoryFrameSource(tmp_path), FakeDetector(_moving_person(1)))

    assert result["ok"] is False
    assert result["error_kind"] == "TOO_FEW_FRAMES"


def test_analyze_empty_directory(tmp_path: Path):
    result = analyze(DirectoryFrameSource(tmp_path), FakeDetector([]))

    assert result["ok"] is False
    assert result["error_kind"] == "NO_FRAMES"


# ---------------------------------------------------------------------------
# run() 的结构化降级
# ---------------------------------------------------------------------------


def test_run_reports_missing_directory(tmp_path: Path):
    request = VisionPipelineRequest(source={"kind": "directory", "path": str(tmp_path / "nope")})

    result = run(request)

    assert result["ok"] is False
    assert result["error_kind"] == "FrameSourceUnavailable"
    assert "目录不存在" in result["error"]


def test_run_reports_missing_weights(tmp_path: Path):
    _write_images(tmp_path, 2)
    request = VisionPipelineRequest(
        source={"kind": "directory", "path": str(tmp_path)},
        detector={"weights_path": str(tmp_path / "nope.pt")},
    )

    result = run(request)

    assert result["ok"] is False
    assert result["error_kind"] == "DetectorUnavailable"
    assert "权重不存在" in result["error"]


def test_request_rejects_blank_path():
    with pytest.raises(ValidationError):
        VisionPipelineRequest(source={"kind": "directory", "path": "   "})


# ---------------------------------------------------------------------------
# 路由（需要 torch 才能构造检测器）
# ---------------------------------------------------------------------------


def test_pipeline_endpoint_returns_structured_response(tmp_path: Path):
    if not runtime_status()["available"]:
        pytest.skip("当前环境没有 torch/torchvision")

    from fastapi.testclient import TestClient

    from app.main import app

    _write_images(tmp_path, 2)
    payload = {
        "source": {"kind": "directory", "path": str(tmp_path), "sample_every_ms": 500},
        "detector": {"pretrained": False, "num_classes": 2, "score_threshold": 0.0},
        "max_frames": 2,
    }

    response = TestClient(app).post("/api/nn/vision-pipeline", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["schema_version"] == "smartops.vision_pipeline.v1"
    assert body["frames_analyzed"] == 2
    assert body["detector"]["license"] == "BSD-3-Clause"
    # 随机初始化权重不保证检出目标，故只断言结构而不是 ok=True
    assert isinstance(body["ok"], bool)


def test_detector_info_is_not_loaded_for_pipeline_spec():
    # build_detector 只做构造，不应触发模型加载
    detector = TorchvisionDetector(weights_path=None, pretrained=False, num_classes=2)
    assert detector.loaded is False
