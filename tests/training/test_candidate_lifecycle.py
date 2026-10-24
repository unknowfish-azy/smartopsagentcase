import pytest

from training.candidate_lifecycle import HumanReview, TrainingCandidate, can_promote, promote


def sample():
    return {"sample_id": "candidate-1", "quality": {"human_review": "NOT_REVIEWED"}}


def test_candidate_requires_ordered_quality_and_review_transitions():
    candidate = TrainingCandidate(sample())
    candidate.transition("VALIDATED")
    candidate.transition("QUALITY_CHECKED")
    candidate.transition("SAFE")
    candidate.transition("REVIEW_PENDING")
    candidate.submit_review(HumanReview("review-1", "candidate-1", "reviewer", "PENDING"))
    assert candidate.state == "REVIEW_PENDING"


def test_candidate_cannot_promote_without_explicit_human_approval():
    candidate = TrainingCandidate(sample())
    for state in ("VALIDATED", "QUALITY_CHECKED", "SAFE", "REVIEW_PENDING"):
        candidate.transition(state)
    candidate.submit_review(HumanReview("review-1", "candidate-1", "reviewer", "APPROVED"))
    assert not can_promote(candidate)
    with pytest.raises(ValueError):
        promote(candidate)


def test_approved_candidate_requires_matching_quality_field():
    candidate = TrainingCandidate(sample())
    for state in ("VALIDATED", "QUALITY_CHECKED", "SAFE", "REVIEW_PENDING"):
        candidate.transition(state)
    candidate.sample["quality"]["human_review"] = "APPROVED"
    candidate.submit_review(HumanReview("review-1", "candidate-1", "reviewer", "APPROVED"))
    assert can_promote(candidate)
    assert promote(candidate)["sample_id"] == "candidate-1"
