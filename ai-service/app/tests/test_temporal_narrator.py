"""P1-3 时序异常语义化测试。"""

import numpy as np
import pytest

from app.services.temporal_narrator import (
    detect_pattern,
    render_template_description,
    narrate,
)


def _make_series(pattern: str, length: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """生成带指定模式的测试时序。"""
    np.random.seed(42)
    base = np.ones(length) * 50.0
    scores = np.zeros(length)

    if pattern == "spike":
        base[50:55] = 200.0
        scores[50:55] = 0.9
    elif pattern == "drop":
        base[50:55] = 5.0
        scores[50:55] = 0.9
    elif pattern == "oscillation":
        base[40:60] = 50 + np.random.randn(20) * 50
        scores[40:60] = 0.8
    elif pattern == "flat":
        pass  # 全部平稳
    return base, scores


def test_detect_spike():
    series, scores = _make_series("spike")
    p = detect_pattern(series, scores)
    assert p.pattern == "sudden_spike"
    assert p.start_idx == 50
    assert p.magnitude > 0


def test_detect_drop():
    series, scores = _make_series("drop")
    p = detect_pattern(series, scores)
    assert p.pattern == "sudden_drop"


def test_detect_oscillation():
    series, scores = _make_series("oscillation")
    p = detect_pattern(series, scores)
    assert p.pattern == "oscillation"
    assert p.volatility > 3.0


def test_detect_flat():
    series, scores = _make_series("flat")
    p = detect_pattern(series, scores)
    assert p.pattern == "flat"
    assert p.start_idx == -1


def test_template_description_not_empty():
    series, scores = _make_series("spike")
    p = detect_pattern(series, scores)
    desc = render_template_description(p)
    assert len(desc) > 0
    assert "上升" in desc or "spike" in desc.lower()


@pytest.mark.asyncio
async def test_narrate_without_llm():
    series, scores = _make_series("spike")
    result = await narrate("cpu_usage", series, scores, llm=None)
    assert "pattern" in result
    assert "description" in result
    assert "template_description" in result
    assert result["llm_enhanced"] is False
    assert result["description"] == result["template_description"]


def test_pattern_to_dict():
    series, scores = _make_series("spike")
    p = detect_pattern(series, scores)
    d = p.to_dict()
    assert d["pattern"] == "sudden_spike"
    assert "magnitude" in d
    assert "volatility" in d
