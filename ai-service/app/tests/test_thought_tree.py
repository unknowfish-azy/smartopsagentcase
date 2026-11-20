"""P1-2 思维树测试。"""

import pytest

from app.services.thought_tree import (
    ThoughtNode,
    ThoughtTreeSearch,
    ToTConfig,
    ValueEstimator,
)


def test_value_estimator_prior():
    est = ValueEstimator()
    node = ThoughtNode("n1", None, 0, "查询日志", "query_logs")
    score, reason = est.estimate(node)
    assert 0 < score <= 1
    assert "先验" in reason


def test_value_estimator_history():
    est = ValueEstimator()
    # 记录 3 次成功
    for _ in range(3):
        est.record_outcome("query_logs", True)
    sr = est.success_rate("query_logs")
    assert sr == 1.0


def test_value_estimator_insufficient_history():
    est = ValueEstimator()
    est.record_outcome("query_logs", True)
    assert est.success_rate("query_logs") is None  # 不足 3 次


def test_value_estimator_depth_penalty():
    est = ValueEstimator()
    shallow = ThoughtNode("n1", None, 0, "查询", "query_logs")
    deep = ThoughtNode("n2", None, 3, "查询", "query_logs")
    s1, _ = est.estimate(shallow)
    s2, _ = est.estimate(deep)
    assert s1 > s2  # 浅层分数更高


@pytest.mark.asyncio
async def test_thought_tree_search():
    config = ToTConfig(max_depth=2, max_branches_per_node=2, beam_width=1)
    search = ThoughtTreeSearch(config)

    async def expand_fn(node):
        return [
            ("思路A", "query_logs", {}),
            ("思路B", "query_metrics", {}),
        ]

    result = await search.search("测试问题", expand_fn, max_iterations=2)
    assert "best_path" in result
    assert "tree" in result
    assert result["total_nodes"] > 1


def test_thought_node_to_dict():
    node = ThoughtNode("n1", None, 0, "测试", "query_logs")
    d = node.to_dict()
    assert d["id"] == "n1"
    assert d["thought"] == "测试"
    assert d["status"] == "pending"
