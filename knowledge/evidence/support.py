"""Claim-evidence support labelling and same-origin de-duplication.

TRUST-L3-P1-01 scope:
- label each (claim, evidence) pair as ``support`` / ``contradiction`` / ``unknown``;
- de-duplicate same-origin / same-content evidence so that repeated chunks
  cannot inflate "independent coverage".

Hard boundary: this is a *lexical heuristic*, not semantic understanding and
not a correctness probability. Only explicit, enumerable cues are handled
(negation words and "partial recovery" wording); everything else stays
``unknown`` instead of being guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Sequence


class SupportLabel(str, Enum):
    """Support label for one claim against the evidence set."""

    SUPPORT = "support"
    CONTRADICTION = "contradiction"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Tokenisation
# ---------------------------------------------------------------------------

_LATIN_RE = re.compile(r"[a-z0-9_]+")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokens(text: str | None) -> set[str]:
    """Tokenise CJK by character bigrams and latin by word.

    The naive ``[\\u4e00-\\u9fff]+`` whole-run matching treats an entire
    Chinese sentence as a single token, which makes overlap ratios collapse to
    0 or 1. Bigrams keep the check cheap while staying discriminative.
    """
    lowered = (text or "").lower()
    result: set[str] = set(_LATIN_RE.findall(lowered))
    for run in _CJK_RUN_RE.findall(lowered):
        if len(run) == 1:
            result.add(run)
        else:
            result.update(run[i:i + 2] for i in range(len(run) - 1))
    return result


# ---------------------------------------------------------------------------
# Cue lexicons (explicit, enumerable)
# ---------------------------------------------------------------------------

NEGATION_CUES: tuple[str, ...] = (
    "未", "没有", "无法", "不能", "不可", "失败", "错误", "报错",
    "不支持", "不兼容", "禁止", "拒绝", "中断", "回滚", "未生效", "未恢复",
    "not ", "cannot", "can't", "failed", "failure", "error",
    "unsupported", "disabled", "rollback", "refused", "denied",
)

PARTIAL_CUES: tuple[str, ...] = (
    "部分", "部分恢复", "部分完成", "尚未完全", "未完全", "仍需", "仅恢复",
    "partially", "partial", "incomplete",
)

SUCCESS_CUES: tuple[str, ...] = (
    "已恢复", "恢复成功", "已成功", "已完成", "已修复", "已生效",
    "恢复正常", "成功", "done", "fixed", "restored", "recovered",
    "resolved", "success",
)

FAILURE_CUES: tuple[str, ...] = (
    "失败", "未恢复", "无法恢复", "未能", "failed", "not recovered",
)

SUPPORT_RATIO_THRESHOLD = 0.5


def _contains_any(text: str, cues: Iterable[str]) -> str | None:
    for cue in cues:
        if cue in text:
            return cue
    return None


def _matched(text: str, cues: Iterable[str]) -> list[str]:
    return sorted({cue for cue in cues if cue in text})


# ---------------------------------------------------------------------------
# Per-claim labelling
# ---------------------------------------------------------------------------

@dataclass
class ClaimSupport:
    """Heuristic support verdict of one claim against the evidence set."""

    claim_provided: bool
    label: SupportLabel
    support_ratio: float
    reason: str
    matched_cues: list[str] = field(default_factory=list)
    evidence_count: int = 0

    @property
    def is_contradiction(self) -> bool:
        return self.label is SupportLabel.CONTRADICTION

    def to_dict(self) -> dict:
        return {
            "claim_provided": self.claim_provided,
            "label": self.label.value,
            "support_ratio": self.support_ratio,
            "reason": self.reason,
            "matched_cues": self.matched_cues,
            "evidence_count": self.evidence_count,
        }


def _contradiction_reason(claim_text: str, evidence_text: str) -> str | None:
    claim_negated = _contains_any(claim_text, NEGATION_CUES) or _contains_any(
        claim_text, FAILURE_CUES
    )
    claim_success = _contains_any(claim_text, SUCCESS_CUES)
    evidence_negated = _contains_any(evidence_text, NEGATION_CUES)
    evidence_partial = _contains_any(evidence_text, PARTIAL_CUES)
    evidence_success = _contains_any(evidence_text, SUCCESS_CUES)

    if claim_success and evidence_partial:
        # A full-success claim against "partially restored" evidence overstates.
        return "partial_recovery_overclaim"
    if claim_success and evidence_negated and not evidence_success:
        return "negated_evidence"
    if claim_negated and evidence_success and not evidence_negated:
        return "success_evidence_against_failure_claim"
    return None


def label_claim(claim: str | None, evidences: Sequence) -> ClaimSupport:
    """Label one claim against a list of ``Evidence`` objects."""
    claim_text = (claim or "").strip().lower()
    evidence_count = len(evidences)

    if not claim_text:
        return ClaimSupport(
            claim_provided=False,
            label=SupportLabel.UNKNOWN,
            support_ratio=0.0,
            reason="claim_not_provided",
            evidence_count=evidence_count,
        )

    if not evidence_count:
        return ClaimSupport(
            claim_provided=True,
            label=SupportLabel.UNKNOWN,
            support_ratio=0.0,
            reason="no_evidence",
            evidence_count=0,
        )

    evidence_text = " ".join((item.content or "") for item in evidences).lower()

    contradiction = _contradiction_reason(claim_text, evidence_text)
    if contradiction:
        return ClaimSupport(
            claim_provided=True,
            label=SupportLabel.CONTRADICTION,
            support_ratio=0.0,
            reason=contradiction,
            matched_cues=_matched(evidence_text, NEGATION_CUES + PARTIAL_CUES),
            evidence_count=evidence_count,
        )

    claim_tokens = tokens(claim_text)
    if not claim_tokens:
        return ClaimSupport(
            claim_provided=True,
            label=SupportLabel.UNKNOWN,
            support_ratio=0.0,
            reason="claim_without_tokens",
            evidence_count=evidence_count,
        )

    overlap = claim_tokens & tokens(evidence_text)
    ratio = round(len(overlap) / len(claim_tokens), 4)

    if ratio >= SUPPORT_RATIO_THRESHOLD:
        return ClaimSupport(
            claim_provided=True,
            label=SupportLabel.SUPPORT,
            support_ratio=ratio,
            reason="lexical_overlap",
            evidence_count=evidence_count,
        )

    # Low overlap: the evidence simply does not establish the claim. This is the
    # "retrieved something, but it does not support the conclusion" case.
    return ClaimSupport(
        claim_provided=True,
        label=SupportLabel.UNKNOWN,
        support_ratio=ratio,
        reason="insufficient_overlap",
        evidence_count=evidence_count,
    )


def label_claims(claims: Sequence[str] | None, evidences: Sequence) -> list[ClaimSupport]:
    return [label_claim(claim, evidences) for claim in (claims or [])]


# ---------------------------------------------------------------------------
# Same-origin de-duplication
# ---------------------------------------------------------------------------

@dataclass
class DedupeResult:
    """De-duplication outcome for coverage accounting."""

    raw_count: int
    unique_content_count: int
    collapsed: int
    unique_document_count: int
    documents: list[str] = field(default_factory=list)
    duplicate_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw_count": self.raw_count,
            "unique_content_count": self.unique_content_count,
            "collapsed": self.collapsed,
            "unique_document_count": self.unique_document_count,
            "documents": self.documents,
            "duplicate_keys": self.duplicate_keys,
        }


def _normalise(text: str | None) -> str:
    return " ".join((text or "").split()).strip().lower()


def _document_key(evidence) -> str:
    source = (getattr(evidence, "source", "") or "").strip()
    if source:
        return source
    return getattr(evidence, "chunk_id", "") or ""


def dedupe_evidences(evidences: Sequence) -> tuple[list, DedupeResult]:
    """Collapse duplicate content and report per-document uniqueness.

    Coverage must be counted on unique *documents*, not on chunk count: several
    chunks from the same document are one source, not several independent
    supports.
    """
    kept: list = []
    seen: dict[str, int] = {}
    duplicate_keys: list[str] = []

    for item in evidences:
        key = f"{_document_key(item)}|{_normalise(getattr(item, 'content', ''))}"
        if key in seen:
            seen[key] += 1
            duplicate_keys.append(key)
            continue
        seen[key] = 1
        kept.append(item)

    documents = sorted({_document_key(item) for item in kept})

    result = DedupeResult(
        raw_count=len(evidences),
        unique_content_count=len(kept),
        collapsed=len(evidences) - len(kept),
        unique_document_count=len(documents),
        documents=documents,
        duplicate_keys=duplicate_keys,
    )
    return kept, result


__all__ = [
    "SupportLabel",
    "ClaimSupport",
    "DedupeResult",
    "label_claim",
    "label_claims",
    "dedupe_evidences",
    "tokens",
]
