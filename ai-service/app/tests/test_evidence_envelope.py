"""DS-01 验收：证据封套的三条不变量与 digest 规则。

digest 断言直接对照 `agent.recovery_contracts.models.object_digest`，
证明封套没有另写一套 canonical 规则。
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.evidence_envelope import EvidenceEnvelope, EvidenceRef

from agent.recovery_contracts.models import object_digest

CAPTURED = datetime(2026, 11, 18, 6, 13, 3, tzinfo=timezone.utc)


def _ref(**overrides) -> EvidenceRef:
    data = {
        "evidence_id": "ev-1",
        "kind": "metric",
        "module": "anomaly_detector",
        "module_version": "0.1.0",
        "captured_at": CAPTURED,
        "derivation": "observed",
        "quality": "ok",
    }
    data.update(overrides)
    return EvidenceRef(**data)


def _kwargs(**overrides) -> dict:
    data = {
        "run_id": "run-1",
        "subject": "order-svc",
        "round": 0,
        "refs": [_ref()],
        "gaps": [],
        "provenance": {"collector": "prometheus"},
    }
    data.update(overrides)
    return data


def _sealed(**overrides) -> EvidenceEnvelope:
    return EvidenceEnvelope.seal(**_kwargs(**overrides))


# --- 不变量 1：空证据必须显式声明缺口 -------------------------------------

def test_empty_refs_without_gaps_rejected():
    with pytest.raises(ValueError, match="gaps"):
        EvidenceEnvelope(**_kwargs(refs=[]))


def test_empty_refs_with_gaps_allowed():
    envelope = EvidenceEnvelope(**_kwargs(refs=[], gaps=["no_trace_for_order_svc"]))
    assert envelope.refs == []
    assert envelope.gaps == ["no_trace_for_order_svc"]


# --- 不变量 2：坏证据不得标为直接观测 -------------------------------------

def test_bad_quality_cannot_be_observed():
    with pytest.raises(ValueError, match="observed"):
        _ref(quality="stale")


# --- 不变量 3：rejection_reason 与 quality 必须一致 -----------------------

def test_rejection_reason_requires_non_ok_quality():
    with pytest.raises(ValueError, match="rejection_reason"):
        _ref(rejection_reason="probe timeout")
    ref = _ref(quality="rejected", derivation="derived", rejection_reason="probe timeout")
    assert ref.quality == "rejected"


def test_naive_captured_at_rejected():
    with pytest.raises(ValueError, match="时区"):
        _ref(captured_at=datetime(2026, 11, 18, 6, 13, 3))


# --- digest：确定性、与 recovery-contract 同规则、时区归一 ----------------

def test_digest_is_deterministic():
    first = _sealed()
    second = _sealed()
    assert first.digest == second.digest
    assert first.digest.startswith("sha256:")
    assert len(first.digest) == len("sha256:") + 64


def test_digest_matches_recovery_contract_canonical_rule():
    envelope = _sealed()
    expected_payload = {
        "run_id": "run-1",
        "subject": "order-svc",
        "round": 0,
        "refs": [
            {
                "evidence_id": "ev-1",
                "kind": "metric",
                "module": "anomaly_detector",
                "module_version": "0.1.0",
                "captured_at": "2026-11-18T06:13:03.000000Z",
                "derivation": "observed",
                "quality": "ok",
                "rejection_reason": None,
                "summary": None,
            }
        ],
        "gaps": [],
        "provenance": {"collector": "prometheus"},
    }
    assert envelope.digest == object_digest(expected_payload)


def test_digest_normalizes_timezone():
    utc = _sealed(refs=[_ref(captured_at=datetime(2026, 11, 18, 6, 13, 3, tzinfo=timezone.utc))])
    shanghai = _sealed(
        refs=[_ref(captured_at=datetime(2026, 11, 18, 14, 13, 3, tzinfo=timezone(timedelta(hours=8))))],
    )
    assert utc.digest == shanghai.digest


# --- 签发后不可改写 -------------------------------------------------------

def test_sealed_envelope_roundtrip_keeps_digest():
    sealed = _sealed()
    assert EvidenceEnvelope(**sealed.model_dump(mode="python")).digest == sealed.digest


def test_sealed_envelope_rejects_mutation():
    sealed = _sealed()
    tampered = {**sealed.model_dump(mode="python"), "subject": "payment-svc"}
    with pytest.raises(ValueError, match="不可改写"):
        EvidenceEnvelope(**tampered)
