"""TRUST-L3-P1-01 tests: separated dimensions, heuristic score, L3 degrade path."""

import pytest

from knowledge.evidence.models import Evidence
from knowledge.evidence.support import SupportLabel, dedupe_evidences, label_claim
from knowledge.evidence.trust_score import (
    INTERPRETATION,
    SCORE_VERSION,
    L3JudgeConfig,
    TrustScoreCalculator,
    build_breakdown,
)


def _evidence(source: str, content: str, score: float = 0.8) -> Evidence:
    return Evidence(
        evidence_id=f"{source}-{content[:8]}",
        chunk_id=f"{source}-chunk",
        source=source,
        content=content,
        score=score,
        version="reference",
        metadata={},
    )


# ---------------------------------------------------------------------------
# Baseline / legacy defect
# ---------------------------------------------------------------------------

def test_empty_evidence_has_zero_trust():
    assert TrustScoreCalculator().calculate([], answer_supported=False) == 0.0


def test_empty_evidence_marks_business_recovery_not_applicable():
    breakdown = build_breakdown([])
    assert breakdown.trust_score == 0.0
    assert breakdown.business_recovery["status"] == "NOT_APPLICABLE"
    assert breakdown.coverage.raw_count == 0


def test_answer_supported_flag_no_longer_inflates_score():
    """旧缺陷回归：有检索结果被当成"结论被支持"。"""
    evidences = [_evidence("nginx.md", "nginx 配置更新", 0.6)]
    calculator = TrustScoreCalculator()

    unsupported = calculator.calculate(evidences, answer_supported=False)
    supported = calculator.calculate(evidences, answer_supported=True)
    unset = calculator.calculate(evidences)

    assert unsupported == supported == unset


def test_score_is_versioned_and_not_a_probability():
    breakdown = build_breakdown([_evidence("a.md", "nginx 配置更新")])
    assert breakdown.score_version == SCORE_VERSION == "heuristic_v1"
    assert breakdown.interpretation == INTERPRETATION
    assert "not_probability" in breakdown.interpretation


# ---------------------------------------------------------------------------
# Dimension 1: retrieval relevance
# ---------------------------------------------------------------------------

def test_retrieval_relevance_is_mean_evidence_score():
    evidences = [
        _evidence("a.md", "nginx 配置更新", 0.9),
        _evidence("b.md", "nginx reload", 0.5),
    ]
    breakdown = build_breakdown(evidences)
    assert breakdown.retrieval_relevance == pytest.approx(0.7)
    assert breakdown.retrieval["count_used"] == 2


# ---------------------------------------------------------------------------
# Dimension 2: per-claim support
# ---------------------------------------------------------------------------

def test_claim_supported_by_overlapping_evidence():
    result = label_claim(
        "nginx 配置更新",
        [_evidence("a.md", "nginx 配置更新：修改 nginx.conf 后 reload")],
    )
    assert result.label is SupportLabel.SUPPORT
    assert result.support_ratio >= 0.5


def test_claim_contradicted_by_negated_evidence():
    result = label_claim(
        "数据库已恢复正常",
        [_evidence("db.md", "数据库未恢复，仍处于故障状态")],
    )
    assert result.label is SupportLabel.CONTRADICTION
    assert result.reason == "negated_evidence"


def test_full_success_claim_over_partial_recovery_is_contradiction():
    result = label_claim(
        "数据库已恢复完成",
        [_evidence("db.md", "部分服务已恢复，其余仍在恢复中")],
    )
    assert result.label is SupportLabel.CONTRADICTION
    assert result.reason == "partial_recovery_overclaim"


def test_retrieved_but_unsupporting_evidence_is_unknown():
    """难例：检索有结果、分数高，但不支撑结论。"""
    result = label_claim(
        "数据库备份失败",
        [_evidence("nginx.md", "nginx 配置更新：修改 nginx.conf 后 reload", 0.95)],
    )
    assert result.label is SupportLabel.UNKNOWN
    assert result.reason == "insufficient_overlap"


def test_no_claim_leaves_support_dimension_unknown():
    breakdown = build_breakdown([_evidence("a.md", "nginx 配置更新")])
    assert breakdown.claim_support is None
    # 未提供结论时按剩余维度重新归一化，不臆造支持分
    assert breakdown.weights_used == {
        "retrieval_relevance": pytest.approx(0.7143),
        "independent_coverage": pytest.approx(0.2857),
    }


# ---------------------------------------------------------------------------
# Dimension 3: independent coverage + same-origin de-duplication
# ---------------------------------------------------------------------------

def test_duplicate_evidence_does_not_inflate_coverage():
    duplicated = _evidence("a.md", "nginx 配置更新")
    evidences = [duplicated, duplicated, _evidence("b.md", "mysql 备份")]
    kept, dedupe = dedupe_evidences(evidences)

    assert dedupe.raw_count == 3
    assert dedupe.unique_content_count == 2
    assert dedupe.collapsed == 1
    assert dedupe.unique_document_count == 2
    assert len(kept) == 2


def test_multiple_chunks_from_one_document_count_as_one_source():
    evidences = [
        _evidence("nginx.md", "nginx 配置更新 第一段"),
        _evidence("nginx.md", "nginx 配置更新 第二段"),
        _evidence("nginx.md", "nginx 配置更新 第三段"),
    ]
    breakdown = build_breakdown(evidences)
    assert breakdown.coverage.unique_document_count == 1
    # 1/3 而不是 3/3，说明多 chunk 不虚增独立覆盖
    assert breakdown.independent_coverage == pytest.approx(0.3333)


def test_three_independent_documents_saturate_coverage():
    evidences = [
        _evidence("a.md", "nginx 配置更新"),
        _evidence("b.md", "mysql 备份"),
        _evidence("c.md", "ssh 连接失败"),
    ]
    breakdown = build_breakdown(evidences)
    assert breakdown.independent_coverage == 1.0


# ---------------------------------------------------------------------------
# Dimension 4: business recovery is never fabricated
# ---------------------------------------------------------------------------

def test_business_recovery_not_applicable_by_default():
    breakdown = build_breakdown([_evidence("a.md", "nginx 配置更新")])
    assert breakdown.business_recovery["status"] == "NOT_APPLICABLE"
    assert "execution" in breakdown.business_recovery["reason"]


# ---------------------------------------------------------------------------
# L3 judge: default passthrough and degrade path
# ---------------------------------------------------------------------------

def _exploding_judge(claim, evidences):
    raise AssertionError("judge must not be called when L3 is disabled")


def test_l3_default_is_passthrough_and_calls_no_judge():
    advice = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=False), judge=_exploding_judge
    ).breakdown(
        [_evidence("a.md", "nginx 配置更新")], claim="nginx 配置更新"
    ).l3
    assert advice.status == "passthrough"
    assert advice.reason == "l3_disabled_by_default"


def test_l3_enabled_without_judge_stays_passthrough():
    advice = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True), judge=None
    ).breakdown(
        [_evidence("a.md", "nginx 配置更新")], claim="nginx 配置更新"
    ).l3
    assert advice.status == "passthrough"
    assert advice.reason == "no_judge_wired"


def test_l3_timeout_is_reported_without_changing_score():
    def slow_judge(claim, evidences):
        import time

        time.sleep(0.5)
        return {"label": "support", "confidence": 0.9}

    calculator = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True, timeout_ms=100), judge=slow_judge
    )
    evidences = [_evidence("a.md", "nginx 配置更新")]
    breakdown = calculator.breakdown(evidences, claim="nginx 配置更新")

    assert breakdown.l3.status == "timeout"
    baseline = TrustScoreCalculator(l3_config=L3JudgeConfig(enabled=False)).breakdown(
        evidences, claim="nginx 配置更新"
    )
    assert breakdown.trust_score == baseline.trust_score


def test_l3_error_is_reported_without_raising():
    def broken_judge(claim, evidences):
        raise RuntimeError("model unavailable")

    breakdown = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True), judge=broken_judge
    ).breakdown([_evidence("a.md", "nginx 配置更新")], claim="nginx 配置更新")

    assert breakdown.l3.status == "error"
    assert "RuntimeError" in breakdown.l3.reason


def test_l3_low_confidence_is_explicit():
    breakdown = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True, min_confidence=0.6),
        judge=lambda claim, evidence: {"label": "support", "confidence": 0.3},
    ).breakdown([_evidence("a.md", "nginx 配置更新")], claim="nginx 配置更新")

    assert breakdown.l3.status == "low_confidence"
    assert breakdown.l3.advice_label == "support"


def test_l3_invalid_label_is_uncertain():
    breakdown = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True),
        judge=lambda claim, evidence: {"label": "maybe", "confidence": 0.9},
    ).breakdown([_evidence("a.md", "nginx 配置更新")], claim="nginx 配置更新")

    assert breakdown.l3.status == "uncertain"


def test_l3_cannot_override_deterministic_contradiction():
    evidences = [_evidence("db.md", "数据库未恢复，仍处于故障状态")]
    breakdown = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True),
        judge=lambda claim, evidence: {"label": "support", "confidence": 0.95},
    ).breakdown(evidences, claim="数据库已恢复正常")

    assert breakdown.claim_support.label is SupportLabel.CONTRADICTION
    assert breakdown.l3.status == "blocked_by_deterministic_contradiction"
    assert breakdown.l3.overrides_deterministic is False


def test_l3_advice_is_suggestion_only():
    breakdown = TrustScoreCalculator(
        l3_config=L3JudgeConfig(enabled=True),
        judge=lambda claim, evidence: {"label": "support", "confidence": 0.9},
    ).breakdown([_evidence("a.md", "nginx 配置更新")], claim="nginx 配置更新")

    assert breakdown.l3.status == "advised"
    assert breakdown.l3.to_dict()["affects_approval"] is False
    assert breakdown.l3.to_dict()["issues_recovery_receipt"] is False


# ---------------------------------------------------------------------------
# KnowledgeService integration
# ---------------------------------------------------------------------------

def test_service_search_exposes_four_dimensions():
    from knowledge.embedding.factory import create_embedding
    from knowledge.service import KnowledgeService

    service = KnowledgeService(embedding=create_embedding("hash"))
    service.add_documents(
        [
            {
                "content": "nginx 配置更新后需要 reload 使配置生效",
                "source": "reference/nginx.md",
                "version": "reference",
            }
        ]
    )
    result = service.search("nginx 配置更新", top_k=3)

    assert isinstance(result["trust_score"], float)
    trust = result["trust"]
    assert set(trust["dimensions"]) == {
        "retrieval_relevance",
        "claim_support",
        "independent_coverage",
        "business_recovery",
    }
    assert trust["score_version"] == SCORE_VERSION
    assert trust["dimensions"]["business_recovery"]["status"] == "NOT_APPLICABLE"
