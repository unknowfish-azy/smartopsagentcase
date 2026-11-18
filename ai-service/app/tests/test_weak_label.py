"""VLM 弱标注候选的纯函数测试。

锁三件事：
1. 模型脏输出（代码围栏、夹带解释、裸数组）能被稳定解析；
2. 越界坐标裁剪、异常框拒绝，且拒绝原因可读 —— 不"修好"成看似可用的框；
3. data.yaml 的类别顺序与 class id 对齐，不然训练会标注错位。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vision.weak_label import (
    CandidateBox,
    build_prompt,
    degenerate_signatures,
    format_yolo_line,
    load_class_names,
    merge_candidate_lines,
    parse_candidates,
)

CLASSES = ["person_intrusion", "obstacle", "fire_or_smoke"]


def test_提示词包含全部类别():
    prompt = build_prompt(CLASSES)

    for name in CLASSES:
        assert f"- {name}" in prompt
    assert '"boxes"' in prompt


def test_提示词不给类别编号():
    """实测坑：类别带 "0: name" 时，模型会把序号一起写进 label 字段。"""
    prompt = build_prompt(CLASSES)

    assert "- 0:" not in prompt
    assert "- 1:" not in prompt


def test_类别名带序号前缀时归一化后再匹配():
    raw = '{"boxes": [{"label": "2: fire_or_smoke", "cx": 0.3, "cy": 0.3, "w": 0.1, "h": 0.1}]}'

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert rejected == []
    assert boxes[0].label == "fire_or_smoke"


def test_类别名大小写与空白可容错():
    raw = '{"boxes": [{"label": " Obstacle ", "cx": 0.3, "cy": 0.3, "w": 0.1, "h": 0.1}]}'

    boxes, _ = parse_candidates(raw, CLASSES)

    assert boxes[0].label == "obstacle"


def test_提示词里不能有可直接照抄的坐标数值():
    """实测坑：qwen2.5vl 会把示例坐标原样吐回来（cx/cy=0.5、w/h=0.2）。

    所以示例必须是尖括号占位符 —— 一旦照抄，JSON 就解析不了，会被如实拒绝，
    而不是产出一个"看起来合法、其实完全错位"的框。
    """
    prompt = build_prompt(CLASSES)

    assert "<小数>" in prompt
    assert "0.50" not in prompt and "0.20" not in prompt


def test_解析标准输出():
    raw = json.dumps(
        {"boxes": [{"label": "obstacle", "cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.3}]}
    )

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert rejected == []
    assert boxes == [CandidateBox(label="obstacle", cx=0.5, cy=0.5, w=0.2, h=0.3)]


def test_解析代码围栏与尾随解释():
    raw = (
        "```json\n"
        '{"boxes": [{"label": "fire_or_smoke", "cx": 0.3, "cy": 0.4, "w": 0.1, "h": 0.1}]}\n'
        "```\n"
        "以上是识别结果，请复核。"
    )

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert rejected == []
    assert boxes[0].label == "fire_or_smoke"


def test_解析裸数组输出():
    raw = '[{"label": "obstacle", "cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.2}]'

    boxes, _ = parse_candidates(raw, CLASSES)

    assert len(boxes) == 1


def test_解析xyxy写法并转中心点():
    raw = '{"boxes": [{"label": "obstacle", "x1": 0.2, "y1": 0.4, "x2": 0.6, "y2": 0.8}]}'

    boxes, _ = parse_candidates(raw, CLASSES)

    assert boxes[0].cx == pytest.approx(0.4)
    assert boxes[0].cy == pytest.approx(0.6)
    assert boxes[0].w == pytest.approx(0.4)
    assert boxes[0].h == pytest.approx(0.4)


def test_越界坐标裁剪进画布():
    raw = '{"boxes": [{"label": "obstacle", "cx": 0.95, "cy": 0.5, "w": 0.3, "h": 0.2}]}'

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert rejected == []
    assert boxes[0].cx + boxes[0].w / 2 <= 1.0
    assert boxes[0].w == pytest.approx(0.2)


def test_未知类别被拒绝并留原因():
    raw = '{"boxes": [{"label": "cat", "cx": 0.5, "cy": 0.5, "w": 0.2, "h": 0.2}]}'

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert boxes == []
    assert "未知类别" in rejected[0]


def test_零尺寸框被拒绝():
    raw = '{"boxes": [{"label": "obstacle", "cx": 0.5, "cy": 0.5, "w": 0.0, "h": 0.2}]}'

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert boxes == []
    assert "框尺寸过小" in rejected[0]


def test_缺坐标字段被拒绝():
    raw = '{"boxes": [{"label": "obstacle", "score": 0.9}]}'

    boxes, rejected = parse_candidates(raw, CLASSES)

    assert boxes == []
    assert "缺少有效坐标字段" in rejected[0]


def test_非JSON输出不抛异常只记账():
    boxes, rejected = parse_candidates("画面里似乎有一个障碍物。", CLASSES)

    assert boxes == []
    assert "JSON 解析失败" in rejected[0]


def test_空结果视为没有候选():
    boxes, rejected = parse_candidates('{"boxes": []}', CLASSES)

    assert boxes == []
    assert rejected == []


def test_格式化成YOLO行():
    box = CandidateBox(label="fire_or_smoke", cx=0.25, cy=0.5, w=0.1, h=0.2)

    assert format_yolo_line(box, CLASSES) == "2 0.250000 0.500000 0.100000 0.200000"


def test_格式化时未知类别直接抛错():
    box = CandidateBox(label="cat", cx=0.5, cy=0.5, w=0.1, h=0.1)

    with pytest.raises(ValueError):
        format_yolo_line(box, CLASSES)


def test_从映射形式data_yaml读类别(tmp_path: Path):
    path = tmp_path / "data.yaml"
    path.write_text(
        "path: /tmp\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: person_intrusion\n"
        "  1: obstacle\n",
        encoding="utf-8",
    )

    assert load_class_names(path) == ["person_intrusion", "obstacle"]


def test_从列表形式data_yaml读类别(tmp_path: Path):
    path = tmp_path / "data.yaml"
    path.write_text("names:\n  - fire_or_smoke\n  - obstacle\n", encoding="utf-8")

    assert load_class_names(path) == ["fire_or_smoke", "obstacle"]


def test_跨图相同坐标判为模型复读():
    """实测坑：qwen2.5vl:3b 在两张不同图上吐出一模一样的 0.3/0.4/0.2/0.2。"""
    repeated = CandidateBox(label="fire_or_smoke", cx=0.3, cy=0.4, w=0.2, h=0.2)

    suspects = degenerate_signatures(
        {"a.jpg": [repeated], "b.jpg": [repeated]}, min_images=2
    )

    assert ("fire_or_smoke", 0.3, 0.4, 0.2, 0.2) in suspects


def test_单图内重复不算复读():
    repeated = CandidateBox(label="obstacle", cx=0.1, cy=0.1, w=0.05, h=0.05)

    assert degenerate_signatures({"a.jpg": [repeated, repeated]}) == set()


def test_坐标有微小差异不算复读():
    left = CandidateBox(label="obstacle", cx=0.301, cy=0.4, w=0.2, h=0.2)
    right = CandidateBox(label="obstacle", cx=0.302, cy=0.4, w=0.2, h=0.2)

    assert degenerate_signatures({"a.jpg": [left], "b.jpg": [right]}) == set()


def test_回写白名单类别到空label():
    candidate = "2 0.350000 0.400000 0.100000 0.150000\n"

    text, added, skipped = merge_candidate_lines("", candidate, {2})

    assert text == candidate
    assert added == 1
    assert skipped == []


def test_回写时白名单外类别静默跳过():
    """missing_extinguisher / fallen_equipment 是系统性误检，按设计不带入真值。"""
    candidate = (
        "3 0.600000 0.490000 0.180000 0.370000\n"
        "2 0.350000 0.400000 0.100000 0.150000\n"
        "4 0.490000 0.450000 0.870000 0.490000\n"
    )

    text, added, skipped = merge_candidate_lines("", candidate, {2})

    assert text == "2 0.350000 0.400000 0.100000 0.150000\n"
    assert added == 1
    assert skipped == []


def test_回写保留人工已标内容():
    existing = "0 0.100000 0.100000 0.050000 0.050000\n"
    candidate = "2 0.350000 0.400000 0.100000 0.150000\n"

    text, added, _ = merge_candidate_lines(existing, candidate, {2})

    assert text.splitlines() == [
        "0 0.100000 0.100000 0.050000 0.050000",
        "2 0.350000 0.400000 0.100000 0.150000",
    ]
    assert added == 1


def test_回写幂等_重复执行不叠加():
    candidate = "2 0.350000 0.400000 0.100000 0.150000\n"

    first, added_first, _ = merge_candidate_lines("", candidate, {2})
    second, added_second, skipped = merge_candidate_lines(first, candidate, {2})

    assert added_first == 1
    assert added_second == 0
    assert second == first
    assert "重复行" in skipped[0]


def test_回写时非法行记账而不是抛错():
    text, added, skipped = merge_candidate_lines("", "not-a-line\n2 0.1 0.2 0.3 0.4\n", {2})

    assert added == 1
    assert "非法行" in skipped[0]
    assert text == "2 0.1 0.2 0.3 0.4\n"


def test_空候选保持原文不变():
    existing = "2 0.350000 0.400000 0.100000 0.150000\n"

    text, added, skipped = merge_candidate_lines(existing, "", {2})

    assert text == existing
    assert added == 0
    assert skipped == []
