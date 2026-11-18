"""VLM 二分类筛图的纯函数测试。

锁四件事：
1. 提示词只问"有没有"，绝口不提坐标 —— 否则又退化成已被证伪的弱标注；
2. `has_target=true` 但类别非法时必须落 uncertain，不能被折叠成 yes 或 no；
3. 模型脏输出（围栏、夹带解释、字符串布尔、裸 bool）有确定行为；
4. 判别力自检能识别"恒定输出"，且不因样本量太小误报。
"""

from __future__ import annotations

from app.vision.screening import (
    MIN_DISCRIMINATION_SAMPLES,
    build_screen_prompt,
    parse_screen_result,
    summarize,
)

CLASSES = ["person_intrusion", "obstacle", "fire_or_smoke"]


def test_提示词包含全部类别():
    prompt = build_screen_prompt(CLASSES)

    for name in CLASSES:
        assert f"- {name}" in prompt
    assert '"has_target"' in prompt


def test_提示词不要求坐标():
    """锁边界：一旦让它报位置，就会回到"坐标靠猜、跨图复读"的老问题。"""
    prompt = build_screen_prompt(CLASSES)

    for token in ("cx", "cy", "x1", "y1", "归一化坐标", "boxes"):
        assert token not in prompt


def test_提示词不给类别编号():
    prompt = build_screen_prompt(CLASSES)

    assert "- 0:" not in prompt


def test_命中且类别合法判yes():
    verdict = parse_screen_result(
        '{"has_target": true, "labels": ["fire_or_smoke"], "confidence": 0.83, "reason": "左侧有烟雾"}',
        CLASSES,
    )

    assert verdict.decision == "yes"
    assert verdict.labels == ("fire_or_smoke",)
    assert verdict.confidence == 0.83
    assert verdict.reason == "左侧有烟雾"


def test_明确无目标判no():
    verdict = parse_screen_result('{"has_target": false, "labels": [], "confidence": 0.9}', CLASSES)

    assert verdict.decision == "no"
    assert verdict.labels == ()
    assert verdict.notes == ()


def test_说没有时忽略模型抄回来的类别():
    """实测坑：模型答 false 仍会把类别清单抄进 labels，采信就会造出一堆假命中。"""
    verdict = parse_screen_result(
        '{"has_target": false, "labels": ["obstacle", "fire_or_smoke"], "confidence": 0.7}',
        CLASSES,
    )

    assert verdict.decision == "no"
    assert verdict.labels == ()


def test_有目标但类别未知判uncertain():
    verdict = parse_screen_result(
        '{"has_target": true, "labels": ["cat"], "confidence": 0.6}', CLASSES
    )

    assert verdict.decision == "uncertain"
    assert verdict.labels == ()
    assert any("未知类别" in note for note in verdict.notes)


def test_有目标但没给类别判uncertain():
    verdict = parse_screen_result('{"has_target": true, "confidence": 0.6}', CLASSES)

    assert verdict.decision == "uncertain"
    assert any("未给出合法类别" in note for note in verdict.notes)


def test_缺少判定字段判uncertain():
    verdict = parse_screen_result('{"labels": ["obstacle"]}', CLASSES)

    assert verdict.decision == "uncertain"
    assert any("has_target" in note for note in verdict.notes)


def test_非JSON输出判uncertain而不抛异常():
    verdict = parse_screen_result("这张图看起来很正常", CLASSES)

    assert verdict.decision == "uncertain"
    assert verdict.notes


def test_代码围栏与尾随解释可解析():
    text = """```json
{"has_target": true, "labels": ["obstacle"], "confidence": 0.5}
```
以上是判断结果。"""
    verdict = parse_screen_result(text, CLASSES)

    assert verdict.decision == "yes"
    assert verdict.labels == ("obstacle",)


def test_字符串布尔与中文布尔都能识别():
    assert parse_screen_result('{"has_target": "true", "labels": ["obstacle"]}', CLASSES).decision == "yes"
    assert parse_screen_result('{"has_target": "是", "labels": ["obstacle"]}', CLASSES).decision == "yes"
    assert parse_screen_result('{"has_target": "no"}', CLASSES).decision == "no"
    assert parse_screen_result('{"has_target": "无"}', CLASSES).decision == "no"


def test_裸布尔输出不当作命中():
    """模型只回一个 true、没有任何类别信息时无法入队标注，只能进 uncertain。"""
    verdict = parse_screen_result("true", CLASSES)

    assert verdict.decision == "uncertain"


def test_类别名带序号前缀可归一():
    verdict = parse_screen_result(
        '{"has_target": true, "labels": ["1: obstacle"]}', CLASSES
    )

    assert verdict.decision == "yes"
    assert verdict.labels == ("obstacle",)


def test_类别名大小写与空白可归一():
    verdict = parse_screen_result(
        '{"has_target": true, "labels": ["  FIRE_OR_SMOKE "]}', CLASSES
    )

    assert verdict.labels == ("fire_or_smoke",)


def test_重复类别去重():
    verdict = parse_screen_result(
        '{"has_target": true, "labels": ["obstacle", "obstacle", "1: obstacle"]}', CLASSES
    )

    assert verdict.labels == ("obstacle",)


def test_置信度缺失为None且超界被裁剪():
    assert parse_screen_result('{"has_target": false}', CLASSES).confidence is None
    assert parse_screen_result('{"has_target": false, "confidence": 3}', CLASSES).confidence == 1.0
    assert parse_screen_result('{"has_target": false, "confidence": -1}', CLASSES).confidence == 0.0
    assert parse_screen_result('{"has_target": false, "confidence": "高"}', CLASSES).confidence is None


def test_理由过长被截断():
    verdict = parse_screen_result(
        '{"has_target": false, "reason": "%s"}' % ("很" * 500), CLASSES
    )

    assert len(verdict.reason) <= 200


def test_正常分布不判定为恒定输出():
    decisions = ["yes"] * 3 + ["no"] * 7

    summary = summarize(decisions)

    assert summary["yes"] == 3
    assert summary["no"] == 7
    assert summary["yes_rate"] == 0.3
    assert summary["low_discrimination"] is False
    assert summary["warning"] == ""


def test_全yes且样本足够判为无判别力():
    decisions = ["yes"] * MIN_DISCRIMINATION_SAMPLES

    summary = summarize(decisions)

    assert summary["yes_rate"] == 1.0
    assert summary["low_discrimination"] is True
    assert "不能作为筛图依据" in summary["warning"]


def test_全no且样本足够判为无判别力():
    decisions = ["no"] * MIN_DISCRIMINATION_SAMPLES

    summary = summarize(decisions)

    assert summary["yes_rate"] == 0.0
    assert summary["low_discrimination"] is True


def test_样本不足时不判定无判别力():
    decisions = ["yes"] * 3

    summary = summarize(decisions)

    assert summary["low_discrimination"] is False


def test_uncertain不计入yes率分母():
    decisions = ["yes", "no", "uncertain", "uncertain"]

    summary = summarize(decisions)

    assert summary["decided"] == 2
    assert summary["yes_rate"] == 0.5
    assert summary["uncertain"] == 2


def test_调用失败单独计数且计入总帧数():
    summary = summarize(["yes", "no"], failed=3)

    assert summary["failed"] == 3
    assert summary["frames"] == 5
    assert summary["decided"] == 2


def test_全uncertain不产生虚假yes率():
    summary = summarize(["uncertain"] * 12)

    assert summary["decided"] == 0
    assert summary["yes_rate"] == 0.0
    assert summary["low_discrimination"] is False
