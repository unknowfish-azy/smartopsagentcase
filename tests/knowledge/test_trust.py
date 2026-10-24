from knowledge.evidence.trust_score import TrustScoreCalculator


def test_empty_evidence_has_zero_trust():
    assert TrustScoreCalculator().calculate([], answer_supported=False) == 0.0


def test_supported_evidence_has_bounded_trust():
    evidence = type("Evidence", (), {"score": 0.8})()
    score = TrustScoreCalculator().calculate([evidence], answer_supported=True)
    assert 0.0 <= score <= 1.0
