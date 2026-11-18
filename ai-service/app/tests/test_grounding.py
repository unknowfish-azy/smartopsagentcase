"""GroundingDINO 后端的纯函数与坐标转换测试。

不联网、不加载权重：模型和 processor 都用桩替换，只验证
「检测器返回的像素框 → 归一化候选框」这一层，以及类别短语的反查规则。
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from app.vision.grounding import (
    DEFAULT_MODEL,
    GroundingDetector,
    _normalize_phrase,
    build_text_prompt,
    match_class,
    nms_keep_indices,
)

CLASSES = ["person_intrusion", "obstacle", "fire_or_smoke"]


class _StubProcessor:
    def __init__(self, boxes, labels):
        self._result = {"boxes": np.array(boxes, dtype=float), "labels": list(labels)}

    def __call__(self, images, text, return_tensors):
        return {"input_ids": _StubTensor()}

    def post_process_grounded_object_detection(self, outputs, input_ids, **kwargs):
        return [self._result]


class _StubTensor:
    def to(self, device):
        return self


class _StubModel:
    def __call__(self, **kwargs):
        return object()


def _detector(boxes, labels) -> GroundingDetector:
    """构造一个已"加载"的检测器，绕过 transformers 与权重下载。"""
    detector = GroundingDetector(model_id=DEFAULT_MODEL, device="cpu")
    detector._processor = _StubProcessor(boxes, labels)
    detector._model = _StubModel()
    return detector


def test_构造不加载权重():
    """边界：import 与构造都必须是零成本，否则 pytest / dry-run 会被 700MB 下载拖死。"""
    detector = GroundingDetector()

    assert detector._model is None
    assert detector._processor is None


def test_类别短语归一():
    assert _normalize_phrase("  Person_Intrusion ") == "person intrusion"
    assert _normalize_phrase("fire-or-smoke") == "fire or smoke"
    assert _normalize_phrase("a   b") == "a b"


def test_提示串按惯例拼接():
    prompt = build_text_prompt(CLASSES)

    assert prompt == "person intrusion. obstacle. fire or smoke."


def test_完整类别短语精确命中():
    assert match_class("fire or smoke", CLASSES) == ("fire_or_smoke", None)
    assert match_class("Obstacle", CLASSES) == ("obstacle", None)


def test_片段短语按词集合归属类别():
    """实测：检测器把 missing extinguisher 切成 extinguisher，把 fallen equipment 切成 equipment。"""
    classes = ["missing_extinguisher", "fallen_equipment", "obstacle"]

    assert match_class("extinguisher", classes) == ("missing_extinguisher", None)
    assert match_class("equipment", classes) == ("fallen_equipment", None)


def test_跨类别拼接的短语被拒绝():
    """`obstacle extinguisher` 不对应任何单一类别，不能挑一个凑数。"""
    classes = ["missing_extinguisher", "obstacle"]

    name, problem = match_class("obstacle extinguisher", classes)

    assert name is None
    assert "未知类别" in problem


def test_一个短语同时落在多个类别上判歧义():
    """类别名共享词根时（obstacle zone / obstacle bar），短语 `obstacle` 无法唯一归属。"""
    classes = ["obstacle zone", "obstacle bar"]

    name, problem = match_class("obstacle", classes)

    assert name is None
    assert "歧义" in problem


def test_完整同名短语优先于包含匹配():
    classes = ["obstacle", "obstacle zone"]

    assert match_class("obstacle", classes) == ("obstacle", None)


def test_完全无关短语被拒绝():
    name, problem = match_class("cat", CLASSES)

    assert name is None
    assert "未知类别" in problem


def test_像素框转归一化中心框():
    detector = _detector([[0.0, 0.0, 100.0, 50.0]], ["obstacle"])
    image = Image.new("RGB", (200, 100))

    boxes, rejected = detector.detect(image, CLASSES)

    assert rejected == []
    assert len(boxes) == 1
    box = boxes[0]
    assert box.label == "obstacle"
    assert (box.cx, box.cy, box.w, box.h) == (0.25, 0.25, 0.5, 0.5)


def test_类别短语大小写与空格可反查():
    detector = _detector([[20.0, 20.0, 80.0, 60.0]], ["Fire_Or_Smoke"])
    image = Image.new("RGB", (200, 100))

    boxes, rejected = detector.detect(image, CLASSES)

    assert rejected == []
    assert boxes[0].label == "fire_or_smoke"


def test_未知类别被拒绝():
    detector = _detector([[0.0, 0.0, 100.0, 50.0]], ["cat"])
    image = Image.new("RGB", (200, 100))

    boxes, rejected = detector.detect(image, CLASSES)

    assert boxes == []
    assert any("未知类别" in note for note in rejected)


def test_越界框被裁剪到画布内():
    detector = _detector([[-50.0, -50.0, 250.0, 150.0]], ["obstacle"])
    image = Image.new("RGB", (200, 100))

    boxes, _ = detector.detect(image, CLASSES)

    assert len(boxes) == 1
    assert boxes[0].cx == 0.5 and boxes[0].cy == 0.5
    assert boxes[0].w == 1.0 and boxes[0].h == 1.0


def test_过小框被拒绝():
    detector = _detector([[10.0, 10.0, 11.0, 11.0]], ["obstacle"])
    image = Image.new("RGB", (200, 100))

    boxes, rejected = detector.detect(image, CLASSES)

    assert boxes == []
    assert any("框尺寸过小" in note for note in rejected)


def test_返回缺少boxes时给出拒绝原因():
    detector = _detector([], [])
    detector._processor.post_process_grounded_object_detection = lambda *a, **k: [{}]
    image = Image.new("RGB", (200, 100))

    boxes, rejected = detector.detect(image, CLASSES)

    assert boxes == []
    assert rejected == ["检测器返回缺少 boxes/labels"]


def test_nms_抑制同类重叠框只留高分():
    boxes = [(0.5, 0.5, 0.2, 0.2), (0.51, 0.51, 0.2, 0.2)]

    kept = nms_keep_indices(boxes, [0.4, 0.9])

    assert kept == [1]


def test_nms_不抑制互不重叠的框():
    boxes = [(0.2, 0.2, 0.1, 0.1), (0.8, 0.8, 0.1, 0.1)]

    kept = nms_keep_indices(boxes, [0.9, 0.8])

    assert sorted(kept) == [0, 1]


def test_nms_空输入返回空():
    assert nms_keep_indices([], []) == []


def test_检测结果中同类重叠框被合并():
    """低阈值下同一目标会出 2 个几乎重合的框，NMS 后只应留一个。"""
    detector = _detector(
        [[20.0, 20.0, 60.0, 60.0], [21.0, 21.0, 61.0, 61.0]],
        ["obstacle", "obstacle"],
    )
    image = Image.new("RGB", (200, 100))

    boxes, _ = detector.detect(image, CLASSES)

    assert len(boxes) == 1
