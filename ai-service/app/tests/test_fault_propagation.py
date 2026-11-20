"""P2-3 故障传播推演测试。"""

import pytest

from app.services.fault_propagation import (
    TopologyEdge,
    propagate,
    assess_impact,
    edges_from_priors,
    find_root_cause_candidates,
)


def _simple_topology() -> list[TopologyEdge]:
    """A → B → C，D 独立。"""
    return [
        TopologyEdge("A", "B", 0.9),
        TopologyEdge("B", "C", 0.8),
    ]


def test_forward_propagation():
    edges = _simple_topology()
    result = propagate("A", edges, max_depth=3, direction="forward")
    affected_ids = {n.node_id for n in result.affected}
    assert "B" in affected_ids
    assert "C" in affected_ids
    assert result.total_affected == 2


def test_forward_probability_decay():
    edges = _simple_topology()
    result = propagate("A", edges, max_depth=3)
    b = next(n for n in result.affected if n.node_id == "B")
    c = next(n for n in result.affected if n.node_id == "C")
    assert b.probability == pytest.approx(0.9)
    assert c.probability == pytest.approx(0.9 * 0.8)
    assert c.probability < b.probability


def test_max_depth_limit():
    edges = _simple_topology()
    result = propagate("A", edges, max_depth=1)
    affected_ids = {n.node_id for n in result.affected}
    assert "B" in affected_ids
    assert "C" not in affected_ids  # 深度 2 被截断


def test_min_probability_filter():
    edges = [TopologyEdge("A", "B", 0.01)]  # 权重极低
    result = propagate("A", edges, min_probability=0.05)
    assert result.total_affected == 0


def test_backward_propagation():
    edges = _simple_topology()
    candidates = find_root_cause_candidates("C", edges)
    candidate_ids = {c.node_id for c in candidates}
    assert "B" in candidate_ids
    assert "A" in candidate_ids


def test_no_cycle():
    """A→B→A 不应死循环。"""
    edges = [
        TopologyEdge("A", "B", 0.9),
        TopologyEdge("B", "A", 0.9),
    ]
    result = propagate("A", edges, max_depth=5)
    # 不应回到 A 自身
    assert all(n.node_id != "A" for n in result.affected)


def test_assess_impact_risk_levels():
    edges = _simple_topology()

    # LOW：无关键服务，影响少
    low = assess_impact("C", edges)  # C 无出边
    assert low["risk_level"] == "LOW"

    # MEDIUM：有影响但无关键服务
    medium = assess_impact("A", edges)
    assert medium["risk_level"] in ("MEDIUM", "HIGH")


def test_assess_impact_critical_hit():
    edges = _simple_topology()
    result = assess_impact("A", edges, critical_services={"C"})
    assert "C" in result["critical_hit"]
    assert result["risk_level"] in ("HIGH", "CRITICAL")


def test_edges_from_priors_default():
    edges = edges_from_priors()
    assert len(edges) > 0
    assert all(isinstance(e, TopologyEdge) for e in edges)


def test_propagation_result_to_dict():
    edges = _simple_topology()
    result = propagate("A", edges)
    d = result.to_dict()
    assert d["source"] == "A"
    assert d["direction"] == "forward"
    assert isinstance(d["affected"], list)
    assert "total_affected" in d
    assert "high_risk_count" in d
