"""Explicit Training Candidate and Human Review lifecycle.

This module is deliberately storage-agnostic. It changes state only when the
caller supplies the relevant validation evidence; it never creates or
auto-approves training samples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


STATES = {
    "CANDIDATE", "VALIDATED", "QUALITY_CHECKED", "SAFE", "REVIEW_PENDING", "APPROVED",
    "INVALID", "UNSAFE", "DUPLICATE", "LEAKAGE", "REJECTED",
}
REVIEW_STATES = {"PENDING", "APPROVED", "REJECTED", "MODIFIED"}
TRANSITIONS = {
    "CANDIDATE": {"VALIDATED", "INVALID"},
    "VALIDATED": {"QUALITY_CHECKED", "UNSAFE", "DUPLICATE", "LEAKAGE"},
    "QUALITY_CHECKED": {"SAFE", "UNSAFE"},
    "SAFE": {"REVIEW_PENDING"},
    "REVIEW_PENDING": {"APPROVED", "REJECTED", "MODIFIED"},
    "MODIFIED": {"VALIDATED", "REJECTED"},
}


@dataclass
class HumanReview:
    review_id: str
    sample_id: str
    reviewer: str
    status: str = "PENDING"
    reason: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __post_init__(self) -> None:
        if self.status not in REVIEW_STATES:
            raise ValueError(f"invalid review status: {self.status}")

    def update(self, status: str, reason: str = "") -> None:
        if status not in REVIEW_STATES:
            raise ValueError(f"invalid review status: {status}")
        self.status = status
        self.reason = reason
        self.updated_at = datetime.now(timezone.utc).isoformat()


@dataclass
class TrainingCandidate:
    sample: dict[str, Any]
    state: str = "CANDIDATE"
    review: HumanReview | None = None
    history: list[str] = field(default_factory=lambda: ["CANDIDATE"])

    def __post_init__(self) -> None:
        if self.state not in STATES:
            raise ValueError(f"invalid candidate state: {self.state}")
        if not isinstance(self.sample.get("sample_id"), str) or not self.sample["sample_id"]:
            raise ValueError("candidate sample_id is required")

    @property
    def sample_id(self) -> str:
        return self.sample["sample_id"]

    def transition(self, state: str) -> None:
        if state not in STATES:
            raise ValueError(f"invalid candidate state: {state}")
        if state not in TRANSITIONS.get(self.state, set()):
            raise ValueError(f"invalid transition: {self.state} -> {state}")
        self.state = state
        self.history.append(state)

    def submit_review(self, review: HumanReview) -> None:
        if review.sample_id != self.sample_id:
            raise ValueError("review sample_id does not match candidate")
        if self.state != "REVIEW_PENDING":
            raise ValueError("candidate must be REVIEW_PENDING before human review")
        self.review = review
        if review.status == "APPROVED":
            self.transition("APPROVED")
        elif review.status == "REJECTED":
            self.transition("REJECTED")
        elif review.status == "MODIFIED":
            self.transition("MODIFIED")


def can_promote(candidate: TrainingCandidate) -> bool:
    """Return true only for explicit human approval, never inferred quality."""
    return (
        candidate.state == "APPROVED"
        and candidate.review is not None
        and candidate.review.status == "APPROVED"
        and candidate.sample.get("quality", {}).get("human_review") == "APPROVED"
    )


def promote(candidate: TrainingCandidate) -> dict[str, Any]:
    if not can_promote(candidate):
        raise ValueError("candidate is not explicitly human-approved")
    return dict(candidate.sample)


__all__ = ["HumanReview", "TrainingCandidate", "can_promote", "promote", "STATES"]
