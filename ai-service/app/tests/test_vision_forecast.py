"""巡检视觉事件预测：跟踪稳定性、轨迹外推、区域事件、降级与样本回流。"""

import json

import pytest
from pydantic import ValidationError

from app.schemas.vision_forecast import (
    VisionFeedbackRequest,
    VisionForecastRequest,
    VisionForecastResponse,
)
from app.services import vision_forecast


def _frame(frame_id, x1, x2, label="person", confidence=0.9, t_ms=None):
    frame = {
        "frame_id": frame_id,
        "detections": [{
            "label": label,
            "confidence": confidence,
            "bbox": [x1, 0.1, x2, 0.3],
        }],
    }
    if t_ms is not None:
        frame["captured_at_ms"] = t_ms
    return frame


def _moving_frames(count=4, start=0.10, step=0.10):
    return [
        _frame(f"f{index}", start + index * step, start + index * step + 0.10,
               t_ms=index * 500.0)
        for index in range(count)
    ]


def test_track_id_stable_and_trajectory_moves_right():
    request = VisionForecastRequest(
        frames=_moving_frames(),
        horizon=3,
        frame_interval_ms=500.0,
    )
    result = VisionForecastResponse(**vision_forecast.forecast(request))

    assert result.mode == "geometric"
    assert len(result.tracks) == 1
    track = result.tracks[0]
    assert track.track_id == "T1"
    assert track.status == "confirmed"
    assert track.hits == 4
    assert track.velocity[0] > 0.1
    xs = [point.cx for point in track.predicted_path]
    assert xs == sorted(xs)
    assert all(point.radius > 0 for point in track.predicted_path)


def test_multiple_labels_do_not_merge():
    frames = [
        {
            "frame_id": f"f{index}",
            "detections": [
                {"label": "person", "confidence": 0.9,
                 "bbox": [0.10 + index * 0.10, 0.10, 0.20 + index * 0.10, 0.30]},
                {"label": "smoke", "confidence": 0.8,
                 "bbox": [0.60, 0.10, 0.70, 0.30]},
            ],
        }
        for index in range(3)
    ]
    result = vision_forecast.forecast(
        VisionForecastRequest(frames=frames, horizon=2, frame_interval_ms=500.0)
    )
    labels = sorted(track["label"] for track in result["tracks"])
    assert labels == ["person", "smoke"]
    assert all(track["hits"] == 3 for track in result["tracks"])


def test_zone_enter_event_has_eta_and_probability():
    request = VisionForecastRequest(
        frames=_moving_frames(),
        zones=[{"zone_id": "cabinet-a", "kind": "danger", "bbox": [0.60, 0.0, 0.90, 0.50]}],
        horizon=3,
        frame_interval_ms=500.0,
    )
    result = vision_forecast.forecast(request)

    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["event"] == "predicted_enter"
    assert event["zone_id"] == "cabinet-a"
    assert event["step"] == 2
    assert event["eta_ms"] == pytest.approx(1000.0)
    assert 0.0 < event["probability"] <= 0.95
    assert "未经校准" in event["basis"][-1]
    assert result["risk_level"] in {"medium", "high"}


def test_dwell_exceeded_uses_measured_history():
    frames = [_frame(f"f{index}", 0.20, 0.30, t_ms=index * 500.0) for index in range(4)]
    request = VisionForecastRequest(
        frames=frames,
        zones=[{"zone_id": "aisle", "kind": "inspect", "bbox": [0.0, 0.0, 1.0, 1.0]}],
        horizon=2,
        dwell_ms=500.0,
    )
    result = vision_forecast.forecast(request)

    events = [event for event in result["events"] if event["event"] == "dwell_exceeded"]
    assert len(events) == 1
    assert events[0]["eta_ms"] == 0.0
    assert any("历史帧实测" in item for item in events[0]["basis"])


def test_sparse_detections_degrade_explicitly():
    frames = [
        _frame("f1", 0.10, 0.20),
        {"frame_id": "f2", "detections": []},
        {"frame_id": "f3", "detections": []},
    ]
    result = vision_forecast.forecast(
        VisionForecastRequest(frames=frames, horizon=2, frame_interval_ms=500.0)
    )

    assert result["model_status"] == "degraded"
    assert result["data_quality"]["status"] == "DEGRADED"
    assert any("检测结果" in item for item in result["risk_basis"])


def test_lost_track_has_no_predicted_path():
    frames = [
        _frame("f1", 0.10, 0.20),
        _frame("f2", 0.12, 0.22),
        {"frame_id": "f3", "detections": []},
        {"frame_id": "f4", "detections": []},
        {"frame_id": "f5", "detections": []},
    ]
    result = vision_forecast.forecast(
        VisionForecastRequest(frames=frames, horizon=3, frame_interval_ms=500.0,
                              lost_after_frames=0)
    )
    lost = [track for track in result["tracks"] if track["status"] == "lost"]
    assert len(lost) == 1
    assert lost[0]["predicted_path"] == []


def test_invalid_bbox_rejected():
    with pytest.raises(ValidationError):
        VisionForecastRequest(frames=[
            {"frame_id": "f1", "detections": [
                {"label": "person", "confidence": 0.9, "bbox": [0.5, 0.1, 0.4, 0.3]},
            ]},
            {"frame_id": "f2", "detections": [
                {"label": "person", "confidence": 0.9, "bbox": [0.6, 0.1, 0.7, 0.3]},
            ]},
        ])


def test_request_without_any_detection_rejected():
    with pytest.raises(ValidationError):
        VisionForecastRequest(frames=[{"frame_id": "f1"}, {"frame_id": "f2"}])


def test_feedback_appends_jsonl(tmp_path):
    payload = VisionFeedbackRequest(
        track_id="T1",
        event="predicted_enter",
        zone_id="cabinet-a",
        predicted=True,
        observed=False,
        frame_id="f42",
    )
    result = vision_forecast.record_feedback(payload.model_dump(), directory=tmp_path)

    assert result["schema_version"] == "smartops.vision_feedback.v1"
    files = list(tmp_path.glob("vision_feedback_*.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert record["track_id"] == "T1"
    assert record["predicted"] is True
    assert record["observed"] is False


def test_model_info_is_honest_about_calibration():
    info = vision_forecast.get_model_info()
    assert info["kind"] == "geometric"
    assert info["probability_calibrated"] is False
    assert "trajectory_extrapolation" in info["supports"]
