"""N05：同证据差分回放的确定性、完整性、变形与篡改反例。"""

from __future__ import annotations

import copy
import json
import socket
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    Claim,
    RecoveryContract,
    canonical_json,
    format_time,
    object_digest,
    parse_time,
    payload_digest,
    replay,
    verify,
)
from agent.recovery_contracts.replay import (
    COMPLETE,
    MALFORMED,
    REPLAY_INCOMPLETE,
    STALE,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _case(name: str = "positive") -> dict:
    return json.loads((FIXTURES / f"vp01-{name}.json").read_text(encoding="utf-8"))


def _resign_contract(raw: dict) -> dict:
    raw["digest"] = object_digest(
        {key: value for key, value in raw.items() if key != "digest"}
    )
    return raw


def _resign_bundle(bundle: dict) -> dict:
    bundle["digest"] = object_digest(
        {key: value for key, value in bundle.items() if key != "digest"}
    )
    return bundle


def _base():
    case = _case()
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])
    receipt = verify(
        contract,
        claim,
        case["input"]["observations"],
        case["decision_time"],
        run_id=case["run_id"],
        verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
        receipt_id="rcpt-replay-base",
    )
    return case, contract, claim, receipt


def _make_bundle(
    case: dict,
    *,
    bundle_id: str = "bundle-positive-r17",
    contract_raw: dict | None = None,
    claim_raw: dict | None = None,
    observations: list[dict] | None = None,
    decision_time: str | None = None,
    policy_version: str = "recovery-eval/v1",
    parent_bundle_id: str | None = None,
    mutation_diff: dict | None = None,
    is_historical_fact: bool = True,
) -> dict:
    contract_raw = copy.deepcopy(
        contract_raw if contract_raw is not None else case["input"]["contract"]
    )
    claim_raw = copy.deepcopy(
        claim_raw if claim_raw is not None else case["input"]["claim"]
    )
    observations = copy.deepcopy(
        observations if observations is not None else case["input"]["observations"]
    )

    probe_map: dict[str, list[str]] = {}
    source_mapping: dict[str, str] = {}
    order: list[str] = []
    for observation in observations:
        probe_map.setdefault(observation["probe_id"], []).append(observation["id"])
        source_mapping[observation["collector_id"]] = observation["source_group"]
        order.append(observation["id"])

    bundle = {
        "schema_version": "recovery-replay/v1",
        "bundle_id": bundle_id,
        "contract": contract_raw,
        "claim": claim_raw,
        "observations": observations,
        "source_mapping": source_mapping,
        "policy_version": policy_version,
        "policy_config": {"selection": "weighted_coverage", "window": "v1"},
        "decision_clock": {
            "mode": "RECORDED",
            "decision_time": decision_time or case["decision_time"],
            "monotonic_origin_id": "mono-run-ver-p0-01",
        },
        "observation_order": order,
        "prerecorded_probe_map": probe_map,
        "budget": {
            "limits": copy.deepcopy(contract_raw["budgets"]),
            "calls_used": len(observations),
            "deadline_at": "2026-11-05T02:00:30Z",
        },
        "run_event_refs": [case["run_id"]],
        "dependency_versions": {
            "python": "3.14",
            "evaluator": "recovery-eval/v1",
        },
        "digest": "sha256:" + "0" * 64,
        "parent_bundle_id": parent_bundle_id,
        "mutation_diff": mutation_diff,
        "is_historical_fact": is_historical_fact,
    }
    return _resign_bundle(bundle)


def _revision_variant(case: dict, base_bundle: dict) -> tuple[dict, RecoveryContract, Claim]:
    contract_raw = copy.deepcopy(case["input"]["contract"])
    contract_raw["expected_revision"] = "r16"
    for obligation in contract_raw["obligations"]:
        obligation["binding_revision"] = "r16"
    contract_raw = _resign_contract(contract_raw)

    claim_raw = copy.deepcopy(case["input"]["claim"])
    claim_raw["contract_digest"] = contract_raw["digest"]
    claim_raw["expected_revision"] = "r16"

    bundle = _make_bundle(
        case,
        bundle_id="bundle-variant-r16",
        contract_raw=contract_raw,
        claim_raw=claim_raw,
        parent_bundle_id=base_bundle["bundle_id"],
        mutation_diff={
            "kind": "EXPECTED_REVISION_CHANGED",
            "field": "expected_revision",
            "from": "r17",
            "to": "r16",
        },
        is_historical_fact=False,
    )
    return bundle, RecoveryContract.from_dict(contract_raw), Claim.from_dict(claim_raw)


def _forbid_network(monkeypatch) -> None:
    def _fail(*args, **kwargs):
        raise AssertionError("回放不得访问网络")

    monkeypatch.setattr(socket.socket, "connect", _fail)
    monkeypatch.setattr(socket, "create_connection", _fail)


# ---------------------------------------------------------------------------
# 完整回放与确定性
# ---------------------------------------------------------------------------

def test_complete_replay_reproduces_recorded_receipt(monkeypatch):
    _forbid_network(monkeypatch)
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )

    assert result.replay_state == COMPLETE
    assert result.verdict == "VERIFIED"
    assert result.recorded_verdict == "VERIFIED"
    assert result.original_receipt_digest == receipt.snapshot_digest()
    assert result.recomputed_receipt_digest == result.original_receipt_digest
    assert result.reason_codes == ()
    assert result.diff_reason_codes == ("VERDICT_UNCHANGED",)
    assert all(not diff.changed for diff in result.obligation_diffs)


def test_replay_is_byte_identical_over_100_runs():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)

    outputs = {
        canonical_json(replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    ).to_dict())
        for _ in range(100)
    }
    assert len(outputs) == 1


def test_replay_never_reads_system_clock(monkeypatch):
    import importlib

    replay_module = importlib.import_module("agent.recovery_contracts.replay")

    class _NoSystemClock(datetime):
        @classmethod
        def now(cls, tz=None):
            raise AssertionError("回放不得读取系统墙钟")

    monkeypatch.setattr(replay_module, "datetime", _NoSystemClock)
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == COMPLETE
    assert result.decision_time == format_time(parse_time(case["decision_time"]))


def test_reversed_observation_order_keeps_same_decision_digest():
    case, contract, claim, receipt = _base()
    observations = list(reversed(case["input"]["observations"]))
    bundle = _make_bundle(case, observations=observations)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == COMPLETE
    assert result.verdict == "VERIFIED"
    assert result.recomputed_receipt_digest == receipt.snapshot_digest()


# ---------------------------------------------------------------------------
# 缺录制证据：REPLAY_INCOMPLETE，不补探、不默认 TRUE
# ---------------------------------------------------------------------------

def test_missing_required_probe_is_incomplete(monkeypatch):
    _forbid_network(monkeypatch)
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)

    result = replay(
        bundle,
        contract,
        claim,
        authorized_scopes=[contract.scope],
        recorded_receipt=receipt,
        required_probes={"probe-c": ["obl-business-health"]},
    )

    assert result.replay_state == REPLAY_INCOMPLETE
    assert result.reason_codes == ("MISSING_RECORDED_PROBE",)
    assert result.verdict is None
    assert result.recomputed_receipt_digest is None
    assert result.obligation_results == ()
    assert [(item.probe_id, item.obligation_ids) for item in result.missing_probes] == [
        ("probe-c", ("obl-business-health",))
    ]


def test_unsupported_policy_version_is_incomplete():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case, policy_version="recovery-eval/v0")

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == REPLAY_INCOMPLETE
    assert result.reason_codes == ("UNSUPPORTED_POLICY_VERSION",)
    assert result.verdict is None


# ---------------------------------------------------------------------------
# 变形回放：同一证据下判定翻转并输出差异原因码
# ---------------------------------------------------------------------------

def test_variant_expected_revision_flips_verified_to_insufficient():
    case, _, _, receipt = _base()
    base_bundle = _make_bundle(case)
    bundle, contract, claim = _revision_variant(case, base_bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )

    assert result.replay_state == COMPLETE
    assert result.recorded_verdict == "VERIFIED"
    assert result.verdict == "INSUFFICIENT"
    assert "VERDICT_FLIPPED" in result.diff_reason_codes
    assert "EXPECTED_REVISION_CHANGED" in result.diff_reason_codes
    diff = result.obligation_diffs[0]
    assert diff.recorded_value == "TRUE"
    assert diff.recomputed_value == "UNKNOWN"
    assert "VALUE_CHANGED" in diff.diff_reason_codes
    assert "WRONG_REVISION" in diff.recomputed_reason_codes


def test_variant_evidence_time_shift_flips_verified_to_insufficient():
    case, contract, claim, receipt = _base()
    observations = copy.deepcopy(case["input"]["observations"])
    for observation in observations:
        observation["observed_at"] = format_time(
            parse_time(observation["observed_at"]) - timedelta(milliseconds=30000)
        )

    bundle = _make_bundle(
        case,
        bundle_id="bundle-variant-time-shift",
        observations=observations,
        parent_bundle_id="bundle-positive-r17",
        mutation_diff={
            "kind": "EVIDENCE_TIME_SHIFTED",
            "field": "observed_at",
            "offset_ms": -30000,
        },
        is_historical_fact=False,
    )

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == COMPLETE
    assert result.verdict == "INSUFFICIENT"
    assert "VERDICT_FLIPPED" in result.diff_reason_codes
    assert "EVIDENCE_TIME_SHIFTED" in result.diff_reason_codes
    assert "STALE" in result.obligation_diffs[0].recomputed_reason_codes


def test_variant_deleted_evidence_flips_verified_to_insufficient():
    case, contract, claim, receipt = _base()
    observations = [
        item for item in case["input"]["observations"]
        if item["id"] != "obs-g3-sg-b"
    ]
    bundle = _make_bundle(
        case,
        bundle_id="bundle-variant-removed",
        observations=observations,
        parent_bundle_id="bundle-positive-r17",
        mutation_diff={
            "kind": "EVIDENCE_REMOVED",
            "removed_evidence_ids": ["obs-g3-sg-b"],
        },
        is_historical_fact=False,
    )

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == COMPLETE
    assert result.verdict == "INSUFFICIENT"
    assert "VERDICT_FLIPPED" in result.diff_reason_codes
    assert "EVIDENCE_REMOVED" in result.diff_reason_codes
    assert "MISSING" in result.obligation_diffs[0].recomputed_reason_codes


# ---------------------------------------------------------------------------
# 篡改/不自洽：拒绝求值并给出明确 reason_code
# ---------------------------------------------------------------------------

def test_tampered_bundle_digest_is_malformed():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["observations"][0]["payload"]["recovery_status"] = False  # 不改 digest

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("BUNDLE_DIGEST_MISMATCH",)
    assert result.verdict is None


def test_tampered_evidence_digest_is_malformed():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["observations"][0]["payload"]["recovery_status"] = False
    _resign_bundle(bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("EVIDENCE_DIGEST_MISMATCH",)


def test_tampered_contract_body_is_malformed():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["contract"]["expected_revision"] = "r16"  # 不同步重签契约 digest
    _resign_bundle(bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("CONTRACT_DIGEST_MISMATCH",)


def test_tampered_claim_digest_is_stale():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["claim"]["scope"] = "tenant:t2/workspace:w9"
    _resign_bundle(bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == STALE
    assert result.reason_codes == ("CLAIM_DIGEST_MISMATCH",)


def test_probe_reference_mismatch_is_malformed():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["observations"][0]["probe_id"] = "probe-z"
    _resign_bundle(bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("PROBE_REFERENCE_MISMATCH",)


def test_observation_order_tamper_is_malformed():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["observation_order"] = bundle["observation_order"][:-1]
    _resign_bundle(bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("OBSERVATION_ORDER_MISMATCH",)


def test_external_expected_digest_mismatch_is_stale():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)

    result = replay(
        bundle,
        contract,
        claim,
        authorized_scopes=[contract.scope],
        recorded_receipt=receipt,
        expected_bundle_digest="sha256:" + "f" * 64,
    )
    assert result.replay_state == STALE
    assert result.reason_codes == ("EXPECTED_DIGEST_MISMATCH",)


def test_mutation_requires_parent_and_non_historical_flag():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(
        case,
        bundle_id="bundle-bad-variant",
        parent_bundle_id="bundle-positive-r17",
        mutation_diff={"kind": "EVIDENCE_REMOVED"},
        is_historical_fact=True,  # 变形包不得自称历史事实
    )

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("MUTATION_DIFF_INCONSISTENT",)


def test_unfrozen_bundle_field_is_rejected():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)
    bundle["extra"] = "not-frozen"
    _resign_bundle(bundle)

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == MALFORMED
    assert result.reason_codes == ("UNFROZEN_FIELD",)


def test_external_expected_digest_match_replays_completely():
    case, contract, claim, receipt = _base()
    bundle = _make_bundle(case)

    result = replay(
        bundle,
        contract,
        claim,
        authorized_scopes=[contract.scope],
        recorded_receipt=receipt,
        expected_bundle_digest=bundle["digest"],
    )
    assert result.replay_state == COMPLETE
    assert result.verdict == "VERIFIED"
    assert result.recomputed_receipt_digest == receipt.snapshot_digest()


# ---------------------------------------------------------------------------
# 增加反例的变形包：与删证据一样必须新 id/新 digest/parent，原包保持不变
# ---------------------------------------------------------------------------

def test_variant_added_counterexample_flips_verified_to_contradicted():
    case, contract, claim, receipt = _base()
    base_bundle = _make_bundle(case)
    parent_snapshot = copy.deepcopy(base_bundle)

    counterexample = copy.deepcopy(case["input"]["observations"][0])
    counterexample.update({
        "id": "obs-counterexample-1",
        "sequence": 9,
        "observed_at": "2026-11-05T02:00:05Z",
        "payload": {"recovery_status": False},
    })
    counterexample["artifact_digest"] = payload_digest(counterexample["payload"])

    observations = copy.deepcopy(case["input"]["observations"]) + [counterexample]
    bundle = _make_bundle(
        case,
        bundle_id="bundle-variant-counterexample",
        observations=observations,
        parent_bundle_id=base_bundle["bundle_id"],
        mutation_diff={
            "kind": "NEW_COUNTEREXAMPLE",
            "added_evidence_ids": ["obs-counterexample-1"],
        },
        is_historical_fact=False,
    )

    result = replay(
        bundle, contract, claim,
        authorized_scopes=[contract.scope], recorded_receipt=receipt,
    )
    assert result.replay_state == COMPLETE
    assert result.recorded_verdict == "VERIFIED"
    assert result.verdict == "CONTRADICTED"
    assert "VERDICT_FLIPPED" in result.diff_reason_codes
    assert "NEW_COUNTEREXAMPLE" in result.diff_reason_codes
    assert result.obligation_diffs[0].recomputed_value == "FALSE"
    assert result.obligation_diffs[0].changed is True

    # 历史原包保持不变：同一冻结输入再次回放仍得到原结论。
    assert base_bundle["digest"] == parent_snapshot["digest"]
    assert base_bundle["observations"] == parent_snapshot["observations"]
    replay(base_bundle, contract, claim,
           authorized_scopes=[contract.scope], recorded_receipt=receipt)


def test_derived_bundle_keeps_parent_replay_unchanged():
    case, contract, claim, receipt = _base()
    base_bundle = _make_bundle(case)
    before = replay(base_bundle, contract, claim,
                    authorized_scopes=[contract.scope], recorded_receipt=receipt).to_dict()

    observations = [
        item for item in case["input"]["observations"] if item["id"] != "obs-g3-sg-b"
    ]
    derived = _make_bundle(
        case,
        bundle_id="bundle-variant-removed-parent-check",
        observations=observations,
        parent_bundle_id=base_bundle["bundle_id"],
        mutation_diff={"kind": "EVIDENCE_REMOVED", "removed_evidence_ids": ["obs-g3-sg-b"]},
        is_historical_fact=False,
    )
    assert derived["parent_bundle_id"] == base_bundle["bundle_id"]
    assert derived["digest"] != base_bundle["digest"]
    assert derived["is_historical_fact"] is False

    after = replay(base_bundle, contract, claim,
                   authorized_scopes=[contract.scope], recorded_receipt=receipt).to_dict()
    assert canonical_json(after) == canonical_json(before)
    assert replay(derived, contract, claim,
                  authorized_scopes=[contract.scope], recorded_receipt=receipt).verdict == "INSUFFICIENT"
