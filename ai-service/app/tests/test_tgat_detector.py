"""P2 阶段 3：TGAT 动态拓扑根因感知测试。"""

import numpy as np
import pytest

from app.schemas.tgat import GraphSnapshot, TGATRequest
from app.schemas.rootcause import AlertNode, AlertEdge
from app.services import tgat_detector
from app.training.tgat_model import (
    NUM_NODE_FEATURES,
    align_nodes,
    heuristic_tgat_scores,
    snapshot_edge_index,
    snapshot_features,
)


def _snapshots_dicts():
    """故障传播：t0 正常 → t1 redis 异常 → t2 redis+gateway 异常（沿调用链扩散）。"""
    return [
        {  # t0：都正常
            "timestamp": 100.0,
            "nodes": [
                {"alert_id": "gateway", "severity": "P3", "status": "CLOSED"},
                {"alert_id": "redis", "severity": "P3", "status": "CLOSED"},
            ],
            "edges": [{"alert_a_id": "gateway", "alert_b_id": "redis"}],
        },
        {  # t1：redis 异常（根因）
            "timestamp": 200.0,
            "nodes": [
                {"alert_id": "gateway", "severity": "P3", "status": "CLOSED"},
                {"alert_id": "redis", "severity": "P0", "status": "OPEN"},
            ],
            "edges": [{"alert_a_id": "gateway", "alert_b_id": "redis"}],
        },
        {  # t2：redis 异常 + gateway 被传染
            "timestamp": 300.0,
            "nodes": [
                {"alert_id": "gateway", "severity": "P1", "status": "OPEN"},
                {"alert_id": "redis", "severity": "P0", "status": "OPEN"},
            ],
            "edges": [{"alert_a_id": "gateway", "alert_b_id": "redis"}],
        },
    ]


def _request(**kw):
    snaps = [GraphSnapshot(**s) for s in _snapshots_dicts()]
    return TGATRequest(snapshots=snaps, **kw)


# ---------------------------------------------------------------------------
# 特征构造
# ---------------------------------------------------------------------------


def test_align_nodes_union():
    order = align_nodes(_snapshots_dicts())
    assert set(order) == {"gateway", "redis"}


def test_snapshot_features_shape_and_mask():
    order = ["gateway", "redis"]
    x, mask = snapshot_features(_snapshots_dicts()[1], order)
    assert x.shape == (2, NUM_NODE_FEATURES)
    assert mask.tolist() == [1.0, 1.0]
    # redis P0 → severity_score 1.0
    assert x[order.index("redis")][0] == 1.0


def test_snapshot_features_missing_node_masked():
    order = ["gateway", "redis", "ghost"]
    x, mask = snapshot_features(_snapshots_dicts()[0], order)
    assert mask[2] == 0.0  # ghost 不在拓扑中
    assert np.all(x[2] == 0.0)


def test_snapshot_edge_index_bidirectional():
    order = ["gateway", "redis"]
    ei = snapshot_edge_index(_snapshots_dicts()[0], order)
    assert ei.shape[0] == 2
    assert ei.shape[1] == 2  # 一条边 → 双向两条


# ---------------------------------------------------------------------------
# heuristic
# ---------------------------------------------------------------------------


def test_heuristic_scores_normalized():
    order = ["gateway", "redis"]
    feats, masks = [], []
    for s in _snapshots_dicts():
        x, m = snapshot_features(s, order)
        feats.append(x)
        masks.append(m)
    scores = heuristic_tgat_scores(feats, masks)
    assert scores.shape == (2,)
    assert scores.max() == pytest.approx(1.0)  # 归一化峰值
    # redis（P0 firing）应高于 gateway
    assert scores[order.index("redis")] >= scores[order.index("gateway")]


# ---------------------------------------------------------------------------
# 主入口 analyze
# ---------------------------------------------------------------------------


def test_analyze_root_candidate_is_redis():
    result = tgat_detector.analyze(_request())
    assert result["ok"] is True
    assert result["mode"] in ("heuristic", "tgat")
    assert result["root_candidates"][0]["alert_id"] == "redis"  # 最早异常 + P0
    assert result["anomaly_score"] > 0.5


def test_analyze_spread_path_order():
    result = tgat_detector.analyze(_request())
    # redis 先异常（t1），gateway 后异常（t2）→ 传播路径 redis 在前
    path = result["spread_path"]
    assert "redis" in path
    assert path.index("redis") < path.index("gateway")


def test_analyze_topology_changes_detected():
    # 构造一个节点上下线的场景
    snaps = _snapshots_dicts()
    snaps.append({  # t3：新增 mysql 节点（扩容）
        "timestamp": 400.0,
        "nodes": snaps[-1]["nodes"] + [{"alert_id": "mysql", "severity": "P2", "status": "OPEN"}],
        "edges": snaps[-1]["edges"],
    })
    request = TGATRequest(snapshots=[GraphSnapshot(**s) for s in snaps])
    result = tgat_detector.analyze(request)
    changed = result["topology_changes"]
    assert any("mysql" in c["added_nodes"] for c in changed)


def test_get_model_info_dynamic():
    info = tgat_detector.get_model_info()
    assert info["dynamic"] is True
    assert info["kind"] in ("heuristic", "tgat")


# ---------------------------------------------------------------------------
# TGAT 模型（torch 可用时）
# ---------------------------------------------------------------------------


def test_tgat_model_predict_shape_and_range():
    pytest.importorskip("torch")
    from app.training.tgat_model import TGATRootCause

    order = ["gateway", "redis"]
    prepared = []
    for s in _snapshots_dicts():
        x, m = snapshot_features(s, order)
        ei = snapshot_edge_index(s, order)
        prepared.append((x, ei, m))

    model = TGATRootCause()
    scores = model.predict(prepared)
    assert scores.shape == (2,)
    assert np.all(scores >= 0.0) and np.all(scores <= 1.0)
