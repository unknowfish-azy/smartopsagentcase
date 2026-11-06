"""VER-P0-01：求值器语义单测（反例集之外的分支）。"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    Claim,
    ContractError,
    RecoveryContract,
    evaluate,
    object_digest,
    verify,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _case(name: str) -> dict:
    return json.loads((FIXTURES / f"vp01-{name}.json").read_text(encoding="utf-8"))


def _resign(contract: dict) -> dict:
    contract["digest"] = object_digest(
        {key: value for key, value in contract.items() if key != "digest"}
    )
    return contract


def _add_obligation(contract: dict, obligation: dict) -> dict:
    contract = copy.deepcopy(contract)
    contract["obligations"].append(obligation)
    return _resign(contract)


def _optional_counter_obligation(contract: dict) -> dict:
    base = contract["obligations"][0]
    obligation = copy.deepcopy(base)
    obligation["obligation_id"] = "obl-optional-reverse"
    obligation["required"] = False
    obligation["predicate_params"] = {"field": "recovery_status", "expected": False}
    return obligation


def test_optional_false_does_not_block_verified():
    case = _case("positive")
    contract_raw = _add_obligation(
        case["input"]["contract"], _optional_counter_obligation(case["input"]["contract"])
    )
    contract = RecoveryContract.from_dict(contract_raw)
    claim = Claim.from_dict({**case["input"]["claim"], "contract_digest": contract.digest})
    evaluation = evaluate(
        contract, claim, case["input"]["observations"], case["decision_time"],
        run_id=case["run_id"], verification_round=case["verification_round"],
    )
    optional = evaluation.obligation_results[1]
    assert optional.value == "FALSE"
    assert evaluation.verdict == "VERIFIED"


def test_timeout_counts_as_failure_only_for_declared_reachability():
    case = _case("negative-timeout")
    contract_raw = copy.deepcopy(case["input"]["contract"])
    obligation = contract_raw["obligations"][0]
    obligation["predicate_id"] = "endpoint_reachable"
    obligation["predicate_params"] = {"timeout_is_failure": True}
    contract_raw = _resign(contract_raw)
    contract = RecoveryContract.from_dict(contract_raw)
    claim = Claim.from_dict(
        {**case["input"]["claim"], "contract_digest": contract.digest}
    )
    evaluation = evaluate(
        contract, claim, case["input"]["observations"], case["decision_time"],
        run_id=case["run_id"], verification_round=case["verification_round"],
    )
    assert evaluation.obligation_results[0].value == "FALSE"
    assert evaluation.verdict == "CONTRADICTED"


def test_contract_without_required_obligation_is_rejected():
    case = _case("positive")
    contract_raw = copy.deepcopy(case["input"]["contract"])
    contract_raw["obligations"][0]["required"] = False
    contract_raw = _resign(contract_raw)
    contract = RecoveryContract.from_dict(contract_raw)
    claim = Claim.from_dict(
        {**case["input"]["claim"], "contract_digest": contract.digest}
    )
    with pytest.raises(ContractError, match="没有 required"):
        evaluate(
            contract, claim, case["input"]["observations"], case["decision_time"],
            run_id=case["run_id"], verification_round=case["verification_round"],
        )


def test_unregistered_predicate_is_rejected():
    case = _case("positive")
    contract_raw = copy.deepcopy(case["input"]["contract"])
    contract_raw["obligations"][0]["predicate_id"] = "llm_judgement"
    contract_raw = _resign(contract_raw)
    contract = RecoveryContract.from_dict(contract_raw)
    with pytest.raises(ContractError, match="未登记的已审核谓词"):
        evaluate(
            contract, None, [], case["decision_time"], run_id="run-x",
            verification_round=1,
        )


def test_claim_bound_to_other_contract_is_rejected():
    case = _case("positive")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(
        {**case["input"]["claim"], "contract_digest": "sha256:" + "0" * 64}
    )
    with pytest.raises(ContractError, match="claim.contract_digest"):
        evaluate(
            contract, claim, case["input"]["observations"], case["decision_time"],
            run_id=case["run_id"], verification_round=1,
        )


def test_unauthorized_scope_is_configurable_by_caller():
    """scope 授权来自服务端身份，不由观测自述决定。"""
    case = _case("negative-cross-scope")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])
    receipt = verify(
        contract, claim, case["input"]["observations"], case["decision_time"],
        run_id=case["run_id"], verification_round=1,
        authorized_scopes=["tenant:t1/workspace:w1", "tenant:t2/workspace:w9"],
    )
    assert receipt.verdict == "VERIFIED"
    assert receipt.target.target_id == "service:edge-nginx"


def test_unqualified_counterexample_blocks_true_slots():
    """R-09：身份未确认的矛盾只构成 UNKNOWN，不得被填满的 TRUE 槽掩盖。"""
    case = _case("positive")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])
    rogue = copy.deepcopy(case["input"]["observations"][0])
    rogue["id"] = "obs-rogue-counter"
    rogue["collector_id"] = "col-unregistered"
    rogue["payload"] = {"recovery_status": False}
    observations = list(case["input"]["observations"]) + [rogue]

    evaluation = evaluate(
        contract, claim, observations, case["decision_time"],
        run_id=case["run_id"], verification_round=case["verification_round"],
    )

    assert evaluation.obligation_results[0].value == "UNKNOWN"
    assert "CONFLICT" in evaluation.obligation_results[0].reason_codes
    assert evaluation.verdict == "INSUFFICIENT"


def test_duplicate_id_with_conflicting_payload_is_order_invariant():
    """R-10：同 ID 相反结论时，输入顺序不得改变 verdict 或证据摘要。"""
    case = _case("positive")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])
    base = list(case["input"]["observations"])
    clone = copy.deepcopy(base[0])
    clone["payload"] = {"recovery_status": False}
    observations = base + [clone]

    forward = verify(
        contract, claim, observations, case["decision_time"],
        run_id=case["run_id"], verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
        receipt_id="rcpt-dup-forward",
    )
    backward = verify(
        contract, claim, list(reversed(observations)), case["decision_time"],
        run_id=case["run_id"], verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
        receipt_id="rcpt-dup-backward",
    )

    assert forward.verdict == backward.verdict == "INSUFFICIENT"
    assert forward.evidence_snapshot_digest == backward.evidence_snapshot_digest


def test_verdict_ignores_non_recovery_signals():
    """StateVerifier.passed / HTTP 200 不是恢复证据。"""
    case = _case("negative-passed-but-business-false")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])
    receipt = verify(
        contract, claim, case["input"]["observations"], case["decision_time"],
        run_id=case["run_id"], verification_round=1,
        authorized_scopes=[case["input"]["contract"]["scope"]],
    )
    assert case["non_recovery_signals"]["state_verifier_passed"] is True
    assert receipt.verdict == "CONTRADICTED"


def test_window_reports_groups_for_positive_case():
    case = _case("positive")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    evaluation = evaluate(
        contract, None, case["input"]["observations"], case["decision_time"],
        run_id=case["run_id"], verification_round=1,
    )
    assert evaluation.window.satisfied is True
    assert evaluation.window.valid_groups == 3
    assert evaluation.window.reasons == []


def test_adjacent_group_gap_over_limit_invalidates_window():
    case = _case("positive")
    observations = copy.deepcopy(case["input"]["observations"])
    shift = timedelta(seconds=6)
    for index in (2, 3):
        moment = datetime.fromisoformat(
            observations[index]["observed_at"].replace("Z", "+00:00")
        )
        observations[index]["observed_at"] = (moment + shift).isoformat().replace(
            "+00:00", "Z"
        )
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    evaluation = evaluate(
        contract, None, observations, "2026-11-05T02:00:12Z",
        run_id=case["run_id"], verification_round=1,
    )
    assert evaluation.window.satisfied is False
    assert "MISSING" in evaluation.window.reasons


def test_empty_observation_set_is_insufficient_not_contradicted():
    case = _case("positive")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    evaluation = evaluate(
        contract, None, [], case["decision_time"],
        run_id=case["run_id"], verification_round=1,
    )
    assert evaluation.verdict == "INSUFFICIENT"
    assert evaluation.obligation_results[0].value == "UNKNOWN"
