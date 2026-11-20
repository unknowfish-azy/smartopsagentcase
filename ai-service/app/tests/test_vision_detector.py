"""A 路线：torchvision FasterRCNN 替代 Ultralytics。

测试分三层：
1. 纯函数（归一化框、YOLO 标注解析、data.yaml 解析、数据自检）——不依赖 torch；
2. 不可用降级——缺权重必须抛带原因的 `DetectorUnavailable`，不许静默返回空；
3. 真实前向——用随机初始化模型跑一张 64x64 图，证明链路通且不联网。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.vision.dataset import (
    dataset_health,
    label_path_for,
    parse_yolo_labels,
    read_data_yaml,
)
from app.vision.detector import (
    DetectorUnavailable,
    TorchvisionDetector,
    detector_info,
    normalize_boxes,
    runtime_status,
)

DATA_YAML = """\
# 巡检检测数据集
path: .
train: images/train
val: images/val

names:
  0: person
  1: cabinet
"""


# ---------------------------------------------------------------------------
# 纯函数
# ---------------------------------------------------------------------------


def test_normalize_boxes_scales_clamps_and_drops_degenerate():
    boxes = normalize_boxes(
        [
            [0, 0, 50, 100],       # 正常
            [90, 0, 200, 100],     # 右越界 → 裁到 1.0
            [10, 10, 10, 40],      # 宽 0 → 丢弃
            [-20, -20, 10, 10],    # 左上越界 → 裁到 0
        ],
        width=100,
        height=100,
    )

    assert boxes[0] == (0.0, 0.0, 0.5, 1.0)
    assert boxes[1] == (0.9, 0.0, 1.0, 1.0)
    assert boxes[2] == (0.0, 0.0, 0.1, 0.1)
    assert len(boxes) == 3  # 退化框被丢弃


def test_normalize_boxes_rejects_bad_image_size():
    with pytest.raises(ValueError):
        normalize_boxes([[0, 0, 1, 1]], width=0, height=10)


def test_parse_yolo_labels_roundtrip(tmp_path: Path):
    label = tmp_path / "a.txt"
    label.write_text("0 0.5 0.5 0.2 0.4\n\n1 0.25 0.75 0.1 0.1\n", encoding="utf-8")

    boxes = parse_yolo_labels(label)

    assert boxes == [(0, 0.5, 0.5, 0.2, 0.4), (1, 0.25, 0.75, 0.1, 0.1)]


def test_parse_yolo_labels_rejects_bad_rows(tmp_path: Path):
    four_columns = tmp_path / "bad1.txt"
    four_columns.write_text("0 0.5 0.5 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="5 列"):
        parse_yolo_labels(four_columns)

    out_of_range = tmp_path / "bad2.txt"
    out_of_range.write_text("0 1.5 0.5 0.2 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不在"):
        parse_yolo_labels(out_of_range)

    zero_width = tmp_path / "bad3.txt"
    zero_width.write_text("0 0.5 0.5 0 0.2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="宽高"):
        parse_yolo_labels(zero_width)


def test_empty_label_file_is_negative_sample(tmp_path: Path):
    label = tmp_path / "empty.txt"
    label.write_text("", encoding="utf-8")
    assert parse_yolo_labels(label) == []


def test_label_path_maps_images_to_labels():
    source = Path("/data/vision/images/train/frame_001.jpg")
    assert label_path_for(source).as_posix() == "/data/vision/labels/train/frame_001.txt"


def _make_dataset(root: Path) -> Path:
    for split, name in (("train", "a"), ("val", "b")):
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)
        (root / "images" / split / f"{name}.jpg").write_bytes(b"not-a-real-jpeg")
    (root / "labels" / "train" / "a.txt").write_text("0 0.5 0.5 0.2 0.2\n1 0.3 0.3 0.1 0.1\n", encoding="utf-8")
    (root / "labels" / "val" / "b.txt").write_text("", encoding="utf-8")
    data_yaml = root / "data.yaml"
    data_yaml.write_text(DATA_YAML, encoding="utf-8")
    return data_yaml


def test_read_data_yaml_resolves_relative_paths(tmp_path: Path):
    data_yaml = _make_dataset(tmp_path)
    parsed = read_data_yaml(data_yaml)

    assert parsed["classes"] == ["person", "cabinet"]
    assert parsed["splits"]["train"] == tmp_path / "images" / "train"
    assert parsed["splits"]["val"] == tmp_path / "images" / "val"


def test_read_data_yaml_rejects_class_index_gap(tmp_path: Path):
    broken = tmp_path / "data.yaml"
    broken.write_text("path: .\ntrain: images/train\n\nnames:\n  0: person\n  2: cabinet\n", encoding="utf-8")
    with pytest.raises(ValueError, match="不连续"):
        read_data_yaml(broken)


def test_dataset_health_counts_negatives_and_flags_out_of_range(tmp_path: Path):
    data_yaml = _make_dataset(tmp_path)
    health = dataset_health(data_yaml)

    assert health["ok"] is True
    assert health["splits"]["train"]["images"] == 1
    assert health["splits"]["train"]["boxes"] == 2
    assert health["splits"]["val"]["empty_labels"] == 1  # 空标注是合法负样本
    assert health["class_histogram"] == {"person": 1, "cabinet": 1}

    (tmp_path / "labels" / "train" / "a.txt").write_text("9 0.5 0.5 0.2 0.2\n", encoding="utf-8")
    broken = dataset_health(data_yaml)
    assert broken["ok"] is False
    assert any("超出范围" in problem for problem in broken["problems"])


# ---------------------------------------------------------------------------
# 运行时状态与降级
# ---------------------------------------------------------------------------


def test_runtime_status_shape_and_license():
    status = runtime_status()
    assert status["backend"].startswith("torchvision.")
    assert status["license"] == "BSD-3-Clause"
    assert isinstance(status["available"], bool)
    if not status["available"]:
        assert status["reason"]


def test_detector_info_is_static_and_honest():
    info = detector_info()
    assert info["available"] in (True, False)
    assert info["license"] == "BSD-3-Clause"
    assert "note" in info


def test_missing_weights_raise_with_reason(tmp_path: Path):
    detector = TorchvisionDetector(weights_path=tmp_path / "nope.pt")
    with pytest.raises(DetectorUnavailable, match="权重不存在"):
        detector.detect(np.zeros((32, 32, 3), dtype=np.uint8))


def test_detector_forward_runs_offline():
    if not runtime_status()["available"]:
        pytest.skip("当前环境没有 torch/torchvision")

    detector = TorchvisionDetector(pretrained=False, num_classes=2, score_threshold=0.0)
    image = np.random.default_rng(0).integers(0, 255, size=(64, 64, 3), dtype=np.uint8)

    detections = detector.detect(image)

    assert isinstance(detections, list)
    for detection in detections:
        assert detection.label  # 类名兜底为 class_N，不允许空串
        assert 0.0 <= detection.confidence <= 1.0
        x1, y1, x2, y2 = detection.bbox
        assert 0.0 <= x1 < x2 <= 1.0
        assert 0.0 <= y1 < y2 <= 1.0


def test_detect_rejects_wrong_shape():
    if not runtime_status()["available"]:
        pytest.skip("当前环境没有 torch/torchvision")

    detector = TorchvisionDetector(pretrained=False, num_classes=2)
    with pytest.raises(ValueError, match="HxWx3"):
        detector.detect(np.zeros((32, 32), dtype=np.uint8))
