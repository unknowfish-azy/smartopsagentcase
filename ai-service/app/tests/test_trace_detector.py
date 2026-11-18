"""P2 阶段 2：TraceFormer 调用链感知测试。"""

import numpy as np
import pytest

from app.schemas.trace import Span, TraceAnalyzeRequest
from app.services import trace_detector
from app.training.trace_model import (
    NUM_FEATURES,
    build_feature_matrix,
    heuristic_span_scores,
    span_to_features,
    _compute_depths,
)


def _spans_dicts():
    """gateway → order → mysql，mysql 慢且错误。"""
    return [
        {"span_id": "s1", "parent_id": None, "service": "gateway", "operation": "GET /order",
         "duration_ms": 1200.0, "status_code": 500},
        {"span_id": "s2", "parent_id": "s1", "service": "order", "operation": "createOrder",
         "duration_ms": 1100.0, "status_code": 200},
        {"span_id": "s3", "parent_id": "s2", "service": "mysql", "operation": "SELECT",
         "duration_ms": 1050.0, "status_code": 200},
        {"span_id": "s4", "parent_id": "s2", "service": "cache", "operation": "GET",
         "duration_ms": 5.0, "status_code": 200},
    ]


def _request(**kw):
    spans = [Span(**s) for s in _spans_dicts()]
    return TraceAnalyzeRequest(trace_id="t-1", spans=spans, **kw)


# ---------------------------------------------------------------------------
# 特征工程
# ---------------------------------------------------------------------------


def test_span_to_features_length_and_error_bit():
    f = span_to_features({"duration_ms": 100, "status_code": 500, "is_error": True}, depth=2)
    assert len(f) == NUM_FEATURES
    assert f[2] == 1.0  # 错误位


def test_compute_depths():
    depths = _compute_depths(_spans_dicts())
    assert depths == [0, 1, 2, 2]  # s1 根，s2 深1，s3/s4 深2


def test_build_feature_matrix_shape():
    m = build_feature_matrix(_spans_dicts())
    assert m.shape == (4, NUM_FEATURES)


# ---------------------------------------------------------------------------
# heuristic 打分
# ---------------------------------------------------------------------------


def test_heuristic_error_span_high_score():
    spans = [{"span_id": "a", "duration_ms": 10, "status_code": 500}]
    scores = heuristic_span_scores(spans)
    assert scores[0] >= 0.9


def test_heuristic_slow_span_score():
    spans = [{"span_id": "a", "duration_ms": 2000, "status_code": 200}]
    scores = heuristic_span_scores(spans, slow_threshold_ms=1000)
    assert scores[0] >= 0.75


def test_heuristic_normal_span_low_score():
    spans = [{"span_id": f"s{i}", "duration_ms": 100 + i, "status_code": 200} for i in range(5)]
    scores = heuristic_span_scores(spans, slow_threshold_ms=1000)
    assert np.all(scores < 0.5)


# ---------------------------------------------------------------------------
# 主入口 analyze
# ---------------------------------------------------------------------------


def test_analyze_returns_structured_evidence():
    result = trace_detector.analyze(_request())

    assert result["ok"] is True
    assert result["trace_id"] == "t-1"
    assert result["mode"] in ("heuristic", "traceformer")
    assert len(result["span_scores"]) == 4
    assert "s1" in result["error_spans"]      # 500 错误
    assert result["anomaly_score"] >= 0.5
    assert result["is_anomaly"] is True
    # top-k 最可疑是 500 错误的 gateway
    assert result["root_candidates"][0]["span_id"] == "s1"
    assert result["explanation"]


def test_analyze_critical_path_dominant_slow_chain():
    result = trace_detector.analyze(_request())
    # 关键路径应是耗时主导的 gateway → order → mysql
    assert result["critical_path"] == ["gateway", "order", "mysql"]


def test_analyze_top_k_limit():
    result = trace_detector.analyze(_request(top_k=2))
    assert len(result["root_candidates"]) == 2


def test_get_model_info():
    info = trace_detector.get_model_info()
    assert "kind" in info
    assert info["kind"] in ("heuristic", "traceformer")


# ---------------------------------------------------------------------------
# TraceFormer 模型（torch 可用时）
# ---------------------------------------------------------------------------


def test_traceformer_forward_and_scores():
    torch = pytest.importorskip("torch")
    from app.training.trace_model import TraceFormer

    model = TraceFormer()
    features = build_feature_matrix(_spans_dicts())
    scores = model.predict_scores(features)

    assert scores.shape == (4,)
    assert np.all(scores >= 0.0) and np.all(scores <= 1.0)  # sigmoid 输出 0-1

    # forward 形状
    x = torch.as_tensor(features).unsqueeze(0)  # [1, 4, F]
    logits = model(x)
    assert logits.shape == (1, 4)
