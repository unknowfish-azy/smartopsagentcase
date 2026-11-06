"""N03：确定性补证调度、run 预算、WAIT/STOP 与同预算固定顺序基线。"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    FIXED_ORDER_POLICY_VERSION,
    SCHEDULER_POLICY_VERSION,
    ContractError,
    ObligationResult,
    Probe,
    ProbeRegistry,
    RecoveryContract,
    RunBudget,
    choose_next,
    choose_next_fixed_order,
    minimum_calls_for_round,
    object_digest,
    parse_time,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DECISION = "2026-11-05T02:00:06Z"


def _case() -> dict:
    return json.loads((FIXTURES / "vp01-positive.json").read_text(encoding="utf-8"))


def _contract() -> RecoveryContract:
    return RecoveryContract.from_dict(_case()["input"]["contract"])


def _two_obligation_contract() -> RecoveryContract:
    raw = copy.deepcopy(_case()["input"]["contract"])
    base = raw["obligations"][0]
    raw["obligations"] = []
    for obligation_id, weight in (("obl-a", 1), ("obl-b", 2)):
        obligation = copy.deepcopy(base)
        obligation["obligation_id"] = obligation_id
        obligation["weight"] = weight
        raw["obligations"].append(obligation)
    raw["digest"] = object_digest({key: value for key, value in raw.items() if key != "digest"})
    return RecoveryContract.from_dict(raw)


def _budget(contract: RecoveryContract | None = None, *, calls_used: int = 0) -> RunBudget:
    contract = contract or _contract()
    return RunBudget.from_contract(
        contract,
        run_id="run-ver-p0-01",
        started_at=DECISION,
        calls_used=calls_used,
    )


def _results(
    contract: RecoveryContract,
    values: dict[str, str] | None = None,
) -> list[ObligationResult]:
    values = values or {}
    checked_at = parse_time(DECISION)
    results: list[ObligationResult] = []
    for obligation in contract.obligations:
        value = values.get(obligation.obligation_id, "UNKNOWN")
        reason_codes = () if value in {"TRUE", "FALSE"} else ("MISSING",)
        results.append(
            ObligationResult(
                obligation_id=obligation.obligation_id,
                value=value,
                reason_codes=reason_codes,
                used_evidence_ids=(),
                rejected_evidence=(),
                checked_at=checked_at,
            )
        )
    return results


def _probe(probe_id: str, **overrides) -> Probe:
    base = {
        "probe_id": probe_id,
        "collector_id": "col-a",
        "collector_version": "1.0.0",
        "obligation_ids": ("obl-business-health",),
        "cost": 1,
        "permission": "probe:read",
        "read_only": True,
        "endpoint": "http://127.0.0.1:18081",
        "path": "/health",
        "target_id": "service:edge-nginx",
        "source_group": "sg-a",
    }
    base.update(overrides)
    return Probe(**base)


def _registry(*probes: Probe) -> ProbeRegistry:
    registry = ProbeRegistry()
    for probe in probes:
        registry.register(probe)
    return registry


def _reasons(decision: dict) -> dict[str, list[str]]:
    return {
        candidate["probe_id"]: candidate["filter_reasons"]
        for candidate in decision["candidates"]
    }


# ---------------------------------------------------------------------------
# 加权覆盖与同分排序
# ---------------------------------------------------------------------------

def test_selects_highest_uncovered_weight_per_cost():
    contract = _two_obligation_contract()
    registry = _registry(
        _probe(
            "probe-wide",
            obligation_ids=("obl-a", "obl-b"),
            collector_id="col-a",
            source_group="sg-a",
            cost=3,
        ),
        _probe(
            "probe-b",
            obligation_ids=("obl-b",),
            collector_id="col-b",
            source_group="sg-b",
            cost=1,
        ),
    )
    decision = choose_next(
        contract, _results(contract), registry, _budget(contract), DECISION,
        permissions={"probe:read"},
    )
    assert decision["decision"] == "SELECTED"
    assert decision["selected_probe_id"] == "probe-b"
    assert decision["score"] == pytest.approx(2.0)
    # choose_next 是纯函数：真正的调用消耗需由调用方记账。
    assert decision["budget_after"]["calls_used"] == 1
    assert decision["budget_before"]["calls_used"] == 0


def test_tie_break_uses_probe_id_lexicographic_order():
    contract = _contract()
    registry = _registry(
        _probe("probe-b", cost=1),
        _probe("probe-a", cost=1),
    )
    decision = choose_next(
        contract, _results(contract), registry, _budget(contract),
        DECISION, permissions={"probe:read"},
    )
    assert decision["selected_probe_id"] == "probe-a"
    assert [item["probe_id"] for item in decision["candidates"]] == ["probe-a", "probe-b"]


def test_decision_is_deterministic_for_identical_inputs():
    contract = _contract()
    registry = _registry(_probe("probe-a"), _probe("probe-b", collector_id="col-b",
                                                   source_group="sg-b"))
    first = choose_next(
        contract, _results(contract), registry, _budget(contract),
        DECISION, permissions={"probe:read"},
    )
    second = choose_next(
        contract, _results(contract), registry, _budget(contract),
        DECISION, permissions={"probe:read"},
    )
    assert first == second
    assert first["decision_id"].startswith("pd-")


# ---------------------------------------------------------------------------
# 过滤顺序与原因
# ---------------------------------------------------------------------------

def test_candidate_filters_cover_permission_executed_exhausted_and_coverage():
    contract = _contract()
    registry = _registry(
        _probe("probe-perm", permission="probe:admin"),
        _probe("probe-exec"),
        _probe("probe-exhausted"),
        _probe("probe-unknown-obligation", obligation_ids=("obl-other",)),
        _probe("probe-identity", collector_id="col-c"),
        _probe("probe-target", target_id="service:other"),
    )
    decision = choose_next(
        contract,
        _results(contract),
        registry,
        _budget(contract),
        DECISION,
        permissions={"probe:read"},
        executed_probe_ids={"probe-exec"},
        exhausted_probe_ids={"probe-exhausted"},
    )
    reasons = _reasons(decision)
    assert reasons["probe-perm"] == ["TOOL_PERMISSION"]
    assert reasons["probe-exec"] == ["DUPLICATE"]
    assert reasons["probe-exhausted"] == ["QUOTA"]
    assert reasons["probe-unknown-obligation"] == ["UNREGISTERED"]
    assert reasons["probe-identity"] == ["IDENTITY"]
    assert reasons["probe-target"] == ["TARGET_ALLOWLIST"]
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "NO_COVERAGE"


def test_cost_over_remaining_budget_is_filtered():
    contract = _contract()
    registry = _registry(_probe("probe-expensive", cost=5))
    decision = choose_next(
        contract, _results(contract), registry, _budget(contract, calls_used=10),
        DECISION, permissions={"probe:read"},
    )
    assert _reasons(decision)["probe-expensive"] == ["COST"]
    assert decision["decision"] == "STOP"


# ---------------------------------------------------------------------------
# 预算 / 轮次 / deadline
# ---------------------------------------------------------------------------

def test_budget_exhausted_stops_with_reason_and_does_not_consume():
    contract = _contract()
    budget = _budget(contract, calls_used=12)
    decision = choose_next(
        contract, _results(contract), _registry(_probe("probe-a")), budget, DECISION,
        permissions={"probe:read"},
    )
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "BUDGET_EXHAUSTED"
    assert decision["selected_probe_id"] is None
    assert decision["budget_after"] == decision["budget_before"]


def test_new_round_does_not_reset_run_budget():
    contract = _contract()
    budget = _budget(contract, calls_used=6)
    budget.start_round(2)
    assert budget.calls_used == 6
    assert budget.calls_remaining == 6

    decision = choose_next(
        contract, _results(contract), _registry(_probe("probe-a")), budget, DECISION,
        permissions={"probe:read"},
    )
    assert decision["decision"] == "SELECTED"
    assert decision["budget_before"]["calls_used"] == 6
    assert decision["budget_after"]["calls_used"] == 7

    budget.record_call()
    assert budget.calls_used == 7
    budget.start_round(3)
    assert budget.calls_used == 7


def test_record_call_cannot_overspend_budget():
    budget = _budget(calls_used=12)
    with pytest.raises(ContractError, match="预算不足"):
        budget.record_call()


def test_deadline_exceeded_stops():
    contract = _contract()
    budget = _budget(contract)
    decision = choose_next(
        contract, _results(contract), _registry(_probe("probe-a")), budget,
        "2026-11-05T02:00:36Z", permissions={"probe:read"},
    )
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "DEADLINE_EXCEEDED"


def test_wait_until_next_slot_without_consuming_budget():
    contract = _contract()
    budget = _budget(contract)
    decision = choose_next(
        contract, _results(contract), _registry(_probe("probe-a")), budget, DECISION,
        permissions={"probe:read"},
        next_slot_at="2026-11-05T02:00:08Z",
    )
    assert decision["decision"] == "WAIT"
    assert decision["selected_probe_id"] is None
    assert decision["next_eligible_at"] == "2026-11-05T02:00:08Z"
    assert decision["stop_reason"] is None
    # 等待不扣探针调用次数。
    assert decision["budget_after"] == decision["budget_before"] == budget.state()


def test_slot_after_deadline_is_deadline_stop():
    contract = _contract()
    decision = choose_next(
        contract, _results(contract), _registry(_probe("probe-a")), _budget(contract),
        DECISION, permissions={"probe:read"},
        next_slot_at="2026-11-05T02:00:40Z",
    )
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "DEADLINE_EXCEEDED"


def test_static_incompatible_when_remaining_budget_cannot_finish_plan():
    contract = _contract()
    budget = _budget(contract, calls_used=7)
    decision = choose_next(
        contract, _results(contract), _registry(_probe("probe-a")), budget, DECISION,
        permissions={"probe:read"},
        required_calls_ahead=10,
    )
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "STATIC_INCOMPATIBLE"
    assert decision["extensions"]["required_calls_ahead"] == 10


# ---------------------------------------------------------------------------
# 反例与无可增益
# ---------------------------------------------------------------------------

def test_required_counterexample_stops_round():
    contract = _contract()
    results = _results(contract, {"obl-business-health": "FALSE"})
    decision = choose_next(
        contract, results, _registry(_probe("probe-a")), _budget(contract), DECISION,
        permissions={"probe:read"},
    )
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "NO_NEW_INFORMATION"
    assert decision["selected_probe_id"] is None
    assert decision["extensions"]["stop_detail"] == "COUNTEREXAMPLE"
    assert decision["extensions"]["counterexample_obligation_ids"] == ["obl-business-health"]


def test_all_required_obligations_true_stops_without_new_information():
    contract = _contract()
    results = _results(contract, {"obl-business-health": "TRUE"})
    decision = choose_next(
        contract, results, _registry(_probe("probe-a")), _budget(contract), DECISION,
        permissions={"probe:read"},
    )
    assert decision["decision"] == "STOP"
    assert decision["stop_reason"] == "NO_NEW_INFORMATION"
    assert "stop_detail" not in decision["extensions"]
    assert _reasons(decision)["probe-a"] == ["DUPLICATE"]


# ---------------------------------------------------------------------------
# 同预算固定顺序基线
# ---------------------------------------------------------------------------

def test_fixed_order_baseline_uses_same_budget_and_probe_id_order():
    contract = _contract()
    registry = _registry(
        _probe("probe-a", cost=5),
        _probe("probe-b", cost=1),
    )
    budget = _budget(contract)
    results = _results(contract)
    greedy = choose_next(
        contract, results, registry, budget, DECISION, permissions={"probe:read"},
    )
    baseline = choose_next_fixed_order(
        contract, results, registry, budget, DECISION, permissions={"probe:read"},
    )

    assert greedy["selected_probe_id"] == "probe-b"
    assert baseline["selected_probe_id"] == "probe-a"
    assert greedy["budget_before"] == baseline["budget_before"]
    assert greedy["budget_after"] == baseline["budget_after"]
    assert baseline["policy_version"] == FIXED_ORDER_POLICY_VERSION
    assert greedy["policy_version"] == SCHEDULER_POLICY_VERSION
    assert baseline["extensions"]["selection_policy"] == "FIXED_ORDER_BY_PROBE_ID"


def test_minimum_calls_for_round_uses_registered_source_groups():
    contract = _contract()
    assert len(contract.source_groups) == 2
    assert minimum_calls_for_round(contract, 2) == 4
    assert minimum_calls_for_round(contract, 0) == 0
