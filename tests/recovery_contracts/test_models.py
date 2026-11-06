"""VER-P0-01：canonical JSON / digest / 冻结约束的读取层测试。"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    Claim,
    ContractError,
    EvidenceObservation,
    ObligationResult,
    RecoveryContract,
    canonical_json,
    digest_of,
    object_digest,
    payload_digest,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _case(name: str = "positive") -> dict:
    return json.loads((FIXTURES / f"vp01-{name}.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# canonical JSON
# ---------------------------------------------------------------------------

def test_canonical_json_sorts_keys_and_drops_whitespace():
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_keeps_array_order():
    assert canonical_json([3, 1, 2]) == "[3,1,2]"


def test_canonical_json_keeps_null_and_rejects_nan():
    assert canonical_json({"a": None}) == '{"a":null}'
    with pytest.raises(ValueError):
        canonical_json({"a": float("nan")})


def test_digest_is_stable_and_prefixed():
    digest = digest_of({"a": 1})
    assert digest == digest_of({"a": 1})
    assert digest.startswith("sha256:")
    assert len(digest) == len("sha256:") + 64


def test_object_digest_ignores_own_digest_field():
    body = {"a": 1}
    assert object_digest({**body, "digest": "sha256:" + "0" * 64}) == object_digest(body)


def test_payload_digest_distinguishes_true_from_string_true():
    assert payload_digest({"ok": True}) != payload_digest({"ok": "true"})


# ---------------------------------------------------------------------------
# RecoveryContract：digest 与冻结常量
# ---------------------------------------------------------------------------

def test_contract_round_trips_without_digest_drift():
    contract = RecoveryContract.from_dict(_case()["input"]["contract"])
    assert RecoveryContract.from_dict(contract.to_dict()) == contract


def test_tampered_contract_is_rejected():
    raw = copy.deepcopy(_case()["input"]["contract"])
    raw["expected_revision"] = "r18"
    with pytest.raises(ContractError, match="digest"):
        RecoveryContract.from_dict(raw)


def test_budget_thresholds_are_frozen():
    raw = copy.deepcopy(_case()["input"]["contract"])
    raw["budgets"]["evidence_ttl_ms"] = 60000
    raw["digest"] = object_digest({k: v for k, v in raw.items() if k != "digest"})
    with pytest.raises(ContractError, match="evidence_ttl_ms 冻结"):
        RecoveryContract.from_dict(raw)


def test_window_thresholds_are_frozen():
    raw = copy.deepcopy(_case()["input"]["contract"])
    raw["window"]["sample_groups"] = 2
    raw["digest"] = object_digest({k: v for k, v in raw.items() if k != "digest"})
    with pytest.raises(ContractError, match="sample_groups 冻结"):
        RecoveryContract.from_dict(raw)


def test_empty_obligations_are_rejected():
    with pytest.raises(ContractError, match="obligations"):
        RecoveryContract.from_dict(_case("negative-empty-obligations")["input"]["contract"])


def test_unknown_contract_field_is_rejected():
    raw = copy.deepcopy(_case()["input"]["contract"])
    raw["unfrozen_field"] = True
    with pytest.raises(ContractError, match="未冻结字段"):
        RecoveryContract.from_dict(raw)


def test_single_source_group_is_rejected():
    raw = copy.deepcopy(_case()["input"]["contract"])
    raw["source_groups"] = ["sg-a"]
    raw["digest"] = object_digest({k: v for k, v in raw.items() if k != "digest"})
    with pytest.raises(ContractError, match="source_groups"):
        RecoveryContract.from_dict(raw)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

def test_claim_rejects_free_text_claim_type():
    raw = copy.deepcopy(_case()["input"]["claim"])
    raw["claim_type"] = "NATURAL_LANGUAGE"
    with pytest.raises(ContractError, match="BUSINESS_RECOVERY"):
        Claim.from_dict(raw)


def test_claim_digest_is_stable():
    claim = Claim.from_dict(_case()["input"]["claim"])
    assert digest_of(claim.to_dict()) == digest_of(claim.to_dict())


# ---------------------------------------------------------------------------
# EvidenceObservation
# ---------------------------------------------------------------------------

def test_observation_requires_payload_or_error():
    raw = copy.deepcopy(_case()["input"]["observations"][0])
    raw.pop("payload")
    with pytest.raises(ContractError, match="payload 与 error"):
        EvidenceObservation.from_dict(raw)


def test_observation_missing_version_key_is_rejected():
    raw = copy.deepcopy(_case("negative-missing-field")["input"]["observations"][0])
    with pytest.raises(ContractError, match="缺字段"):
        EvidenceObservation.from_dict(raw)


def test_observation_rejects_elapsed_over_probe_timeout():
    raw = copy.deepcopy(_case()["input"]["observations"][0])
    raw["elapsed_ms"] = 1500
    with pytest.raises(ContractError, match="elapsed_ms"):
        EvidenceObservation.from_dict(raw)


def test_observation_null_revision_is_allowed_by_schema():
    raw = copy.deepcopy(_case()["input"]["observations"][0])
    raw["observed_revision"] = None
    observation = EvidenceObservation.from_dict(raw)
    assert observation.observed_revision is None


# ---------------------------------------------------------------------------
# ObligationResult 不变式
# ---------------------------------------------------------------------------

def test_true_result_must_not_carry_reason_codes():
    with pytest.raises(ContractError, match="不得带原因码"):
        ObligationResult(
            obligation_id="obl-1",
            value="TRUE",
            reason_codes=("MISSING",),
            used_evidence_ids=("obs-1",),
            rejected_evidence=(),
            checked_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        )


def test_unknown_result_must_carry_reason_codes():
    with pytest.raises(ContractError, match="至少一个原因码"):
        ObligationResult(
            obligation_id="obl-1",
            value="UNKNOWN",
            reason_codes=(),
            used_evidence_ids=(),
            rejected_evidence=(),
            checked_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        )


def test_result_rejects_unknown_reason_code():
    with pytest.raises(ContractError, match="原因码非法"):
        ObligationResult(
            obligation_id="obl-1",
            value="UNKNOWN",
            reason_codes=("UNSUPPORTED",),
            used_evidence_ids=(),
            rejected_evidence=(),
            checked_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        )
