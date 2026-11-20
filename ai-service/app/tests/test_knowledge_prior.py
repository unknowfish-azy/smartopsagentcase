"""P1-1 知识先验服务测试。"""

import pytest

from app.services.knowledge_prior import (
    BUILTIN_RULES,
    ALLOWED_NODE_TYPES,
    ALLOWED_RELATIONS,
    PriorRule,
    build_node_priors,
    parse_llm_rules,
)


def test_builtin_rules_valid():
    """内置规则全部通过白名单校验。"""
    for rule in BUILTIN_RULES:
        assert rule.source in ALLOWED_NODE_TYPES
        assert rule.target in ALLOWED_NODE_TYPES
        assert rule.relation in ALLOWED_RELATIONS
        assert 0 < rule.weight <= 1


def test_parse_llm_rules_valid_format():
    raw = """
redis | blocks | gateway | 0.85
mysql | connection_exhausted | api_service | 0.90
"""
    rules = parse_llm_rules(raw)
    assert len(rules) == 2
    assert rules[0].source == "redis"
    assert rules[0].weight == 0.85
    assert rules[0].source_type == "llm"


def test_parse_llm_rules_rejects_invalid():
    raw = """
invalid_node | blocks | gateway | 0.85
redis | invalid_relation | gateway | 0.85
redis | blocks | gateway | 1.5
redis | blocks | gateway | abc
redis | blocks | gateway
"""
    rules = parse_llm_rules(raw)
    assert len(rules) == 0


def test_parse_llm_rules_skips_comments():
    raw = """
# comment
// another comment
redis | blocks | gateway | 0.85
"""
    rules = parse_llm_rules(raw)
    assert len(rules) == 1


def test_build_node_priors():
    priors = build_node_priors(["redis", "gateway", "mysql"])
    assert "redis" in priors
    assert "gateway" in priors
    assert "mysql" in priors
    # redis 有出边（blocks gateway, slow_response api_service）
    assert len(priors["redis"].outgoing) > 0
    # gateway 有入边
    assert len(priors["gateway"].incoming) > 0


def test_node_prior_feature_vector():
    priors = build_node_priors(["redis", "gateway"])
    vec = priors["redis"].to_feature_vector()
    assert len(vec) == 5
    assert vec[0] == priors["redis"].importance  # 重要度
    assert vec[1] > 0  # 出边数 > 0


def test_node_prior_importance():
    priors = build_node_priors(["redis"])
    # redis 有两条出边：0.85 + 0.75 = 1.60
    assert priors["redis"].importance == pytest.approx(1.60, abs=0.01)
