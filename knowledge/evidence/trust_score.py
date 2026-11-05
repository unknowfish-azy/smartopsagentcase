"""Heuristic evidence-support trust score (versioned).

TRUST-L3-P1-01 splits what used to be one opaque number into four separate
dimensions:

1. ``retrieval_relevance``   - mean retrieval score of the used evidence;
2. ``claim_support``         - per-conclusion label (support / contradiction / unknown);
3. ``independent_coverage``  - coverage counted on de-duplicated documents;
4. ``business_recovery``     - business recovery verification (owned by the
   execution side; NOT_APPLICABLE here, never faked).

``trust_score`` stays a *heuristic* evidence-support score with an explicit
``score_version``. It is **not** a correctness probability and must not be
interpreted as one. Any additional field here is additive: consumers such as
ai-service keep reading the plain float.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from .support import (
    ClaimSupport,
    DedupeResult,
    SupportLabel,
    dedupe_evidences,
    label_claim,
)

# Bumping this invalidates comparisons with older stored scores.
SCORE_VERSION = "heuristic_v1"
INTERPRETATION = "heuristic_evidence_support_score_not_probability"

WEIGHTS = {
    "retrieval_relevance": 0.5,
    "claim_support": 0.3,
    "independent_coverage": 0.2,
}

# Coverage saturates after this many independent documents.
COVERAGE_TARGET_DOCUMENTS = 3


# ---------------------------------------------------------------------------
# L3 limited judge (suggestion only)
# ---------------------------------------------------------------------------

@dataclass
class L3JudgeConfig:
    """Optional L3 judge switch. Default is passthrough (no judge call)."""

    enabled: bool = False
    timeout_ms: int = 800
    min_confidence: float = 0.6


@dataclass
class L3Advice:
    """Outcome of the optional L3 judge.

    ``advice_label`` is a *suggestion*; it never rewrites the deterministic
    label, never touches approval and never signs a recovery receipt.
    """

    status: str
    advice_label: str | None = None
    confidence: float | None = None
    latency_ms: float | None = None
    reason: str = ""
    overrides_deterministic: bool = False

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "advice_label": self.advice_label,
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "reason": self.reason,
            "overrides_deterministic": self.overrides_deterministic,
            "affects_approval": False,
            "issues_recovery_receipt": False,
        }


_VALID_LABELS = {label.value for label in SupportLabel}


def advise_l3(
    claim: str | None,
    evidences: Sequence,
    config: L3JudgeConfig | None = None,
    judge: Callable[[str, Sequence], Any] | None = None,
    deterministic: ClaimSupport | None = None,
) -> L3Advice:
    """Run the optional L3 judge with an explicit timeout and degrade path."""
    cfg = config or L3JudgeConfig()

    if not cfg.enabled:
        return L3Advice(status="passthrough", reason="l3_disabled_by_default")

    if judge is None:
        return L3Advice(status="passthrough", reason="no_judge_wired")

    if not (claim or "").strip():
        return L3Advice(status="passthrough", reason="claim_not_provided")

    from time import perf_counter

    started = perf_counter()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(judge, claim, evidences)
        raw = future.result(timeout=cfg.timeout_ms / 1000.0)
    except FutureTimeout:
        return L3Advice(
            status="timeout",
            reason=f"judge_exceeded_{cfg.timeout_ms}ms",
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )
    except Exception as exc:  # judge failure must never break the pipeline
        return L3Advice(
            status="error",
            reason=f"judge_error:{type(exc).__name__}",
            latency_ms=round((perf_counter() - started) * 1000, 2),
        )
    finally:
        executor.shutdown(wait=False)

    latency = round((perf_counter() - started) * 1000, 2)

    if not isinstance(raw, dict):
        return L3Advice(status="uncertain", reason="judge_output_not_dict", latency_ms=latency)

    label = str(raw.get("label") or "").strip().lower()
    if label not in _VALID_LABELS:
        return L3Advice(
            status="uncertain",
            reason=f"judge_label_invalid:{label or 'empty'}",
            latency_ms=latency,
        )

    try:
        confidence = float(raw.get("confidence"))
    except (TypeError, ValueError):
        return L3Advice(status="uncertain", reason="judge_confidence_missing", latency_ms=latency)

    if confidence < cfg.min_confidence:
        return L3Advice(
            status="low_confidence",
            advice_label=label,
            confidence=round(confidence, 4),
            reason=f"below_min_confidence_{cfg.min_confidence}",
            latency_ms=latency,
        )

    if deterministic is not None and deterministic.is_contradiction and label != SupportLabel.CONTRADICTION.value:
        # A deterministic contradiction from explicit cues outranks model advice.
        return L3Advice(
            status="blocked_by_deterministic_contradiction",
            advice_label=label,
            confidence=round(confidence, 4),
            reason="deterministic_contradiction_kept",
            latency_ms=latency,
            overrides_deterministic=False,
        )

    return L3Advice(
        status="advised",
        advice_label=label,
        confidence=round(confidence, 4),
        reason="judge_suggestion_only",
        latency_ms=latency,
        overrides_deterministic=False,
    )


# ---------------------------------------------------------------------------
# Breakdown
# ---------------------------------------------------------------------------

@dataclass
class TrustBreakdown:
    """Four separated dimensions plus the versioned heuristic score."""

    trust_score: float
    score_version: str = SCORE_VERSION
    interpretation: str = INTERPRETATION
    retrieval_relevance: float = 0.0
    retrieval: dict = field(default_factory=dict)
    claim_support: ClaimSupport | None = None
    independent_coverage: float = 0.0
    coverage: DedupeResult | None = None
    business_recovery: dict = field(default_factory=dict)
    l3: L3Advice | None = None
    weights_used: dict = field(default_factory=dict)
    legacy_answer_supported_ignored: bool = False

    def to_dict(self) -> dict:
        return {
            "trust_score": self.trust_score,
            "score_version": self.score_version,
            "interpretation": self.interpretation,
            "weights_used": self.weights_used,
            "dimensions": {
                "retrieval_relevance": {
                    "value": self.retrieval_relevance,
                    "detail": self.retrieval,
                },
                "claim_support": (
                    self.claim_support.to_dict()
                    if self.claim_support is not None
                    else {"available": False, "reason": "not_evaluated"}
                ),
                "independent_coverage": {
                    "value": self.independent_coverage,
                    "detail": self.coverage.to_dict() if self.coverage else {},
                },
                "business_recovery": self.business_recovery,
            },
            "l3": self.l3.to_dict() if self.l3 is not None else {"status": "passthrough"},
            "legacy_answer_supported_ignored": self.legacy_answer_supported_ignored,
        }


def _coverage_value(dedupe: DedupeResult) -> float:
    return round(min(dedupe.unique_document_count / float(COVERAGE_TARGET_DOCUMENTS), 1.0), 4)


def build_breakdown(
    evidences: Sequence,
    claim: str | None = None,
    *,
    l3_config: L3JudgeConfig | None = None,
    judge: Callable[[str, Sequence], Any] | None = None,
    business_recovery: dict | None = None,
) -> TrustBreakdown:
    """Compute the separated dimensions and the versioned heuristic score."""
    raw_count = len(evidences)

    if raw_count == 0:
        return TrustBreakdown(
            trust_score=0.0,
            retrieval={},
            claim_support=label_claim(claim, []) if (claim or "").strip() else None,
            coverage=DedupeResult(0, 0, 0, 0, [], []),
            business_recovery=business_recovery
            or {"status": "NOT_APPLICABLE", "reason": "no_evidence"},
            l3=advise_l3(claim, [], l3_config, judge),
            weights_used={},
        )

    kept, dedupe = dedupe_evidences(evidences)

    retrieval_relevance = round(
        sum(float(getattr(item, "score", 0.0) or 0.0) for item in kept) / len(kept),
        4,
    )
    retrieval_detail = {
        "count_used": len(kept),
        "count_raw": raw_count,
        "mean_score": retrieval_relevance,
        "max_score": round(
            max(float(getattr(item, "score", 0.0) or 0.0) for item in kept), 4
        ),
    }

    claim_support = label_claim(claim, kept) if (claim or "").strip() else None

    coverage_value = _coverage_value(dedupe)

    # Unavailable dimensions are dropped and the remaining weights renormalised
    # instead of silently inventing a value.
    available: dict[str, float] = {"retrieval_relevance": retrieval_relevance,
                                   "independent_coverage": coverage_value}
    if claim_support is not None:
        available["claim_support"] = (
            1.0 if claim_support.label is SupportLabel.SUPPORT
            else 0.0 if claim_support.label is SupportLabel.CONTRADICTION
            else 0.5  # unknown: evidence does not establish the claim
        )

    used_weights = {name: WEIGHTS[name] for name in available}
    total_weight = sum(used_weights.values())
    normalised = {name: round(weight / total_weight, 4) for name, weight in used_weights.items()}

    score = sum(available[name] * normalised[name] for name in available)
    score = round(max(0.0, min(score, 1.0)), 4)

    return TrustBreakdown(
        trust_score=score,
        retrieval_relevance=retrieval_relevance,
        retrieval=retrieval_detail,
        claim_support=claim_support,
        independent_coverage=coverage_value,
        coverage=dedupe,
        business_recovery=business_recovery
        or {"status": "NOT_APPLICABLE", "reason": "owned_by_execution_side"},
        l3=advise_l3(claim, kept, l3_config, judge, deterministic=claim_support),
        weights_used=normalised,
    )


class TrustScoreCalculator:
    """Backward-compatible facade returning the plain heuristic float."""

    def __init__(
        self,
        *,
        l3_config: L3JudgeConfig | None = None,
        judge: Callable[[str, Sequence], Any] | None = None,
    ) -> None:
        self.l3_config = l3_config or L3JudgeConfig()
        self.judge = judge

    def calculate(
        self,
        evidences,
        answer_supported: bool | None = None,
        claim: str | None = None,
    ) -> float:
        """Return ``trust_score`` only.

        ``answer_supported`` is kept for signature compatibility but is **not**
        used: "retrieved something" must never be treated as "conclusion
        supported", which is exactly the defect this task fixes.
        """
        return self.breakdown(evidences, claim=claim).trust_score

    def breakdown(
        self,
        evidences,
        claim: str | None = None,
        business_recovery: dict | None = None,
    ) -> TrustBreakdown:
        return build_breakdown(
            evidences,
            claim=claim,
            l3_config=self.l3_config,
            judge=self.judge,
            business_recovery=business_recovery,
        )


__all__ = [
    "SCORE_VERSION",
    "INTERPRETATION",
    "WEIGHTS",
    "L3JudgeConfig",
    "L3Advice",
    "TrustBreakdown",
    "TrustScoreCalculator",
    "build_breakdown",
    "advise_l3",
]
