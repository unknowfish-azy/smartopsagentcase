"""N08 独立 oracle 与实现的对照测试。

这些测试不修改实现、不修改现有样例：它们把 docs/design/recovery-contract-v1/examples
与实验脚本里的构造案例作为同一批输入，分别交给独立 oracle 和被测实现。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "scripts" / "research" / "recovery_contracts"
for path in (str(ROOT), str(SCRIPT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

import independent_oracle  # noqa: E402
import run_experiments  # noqa: E402


def _all_cases() -> list[run_experiments.Case]:
    return run_experiments.load_example_cases() + run_experiments.build_custom_cases()


def _case(case_id: str) -> run_experiments.Case:
    for case in _all_cases():
        if case.case_id == case_id:
            return case
    raise AssertionError(f"未找到案例：{case_id}")


def _oracle_decision(case: run_experiments.Case) -> Any:
    return independent_oracle.judge(
        case.contract,
        case.observations,
        case.decision_time,
        run_id=case.run_id,
        verification_round=case.verification_round,
        authorized_scopes=case.authorized_scopes,
        claim=case.claim,
    )


# ---------------------------------------------------------------------------
# 一致案例
# ---------------------------------------------------------------------------

def test_positive_agrees_on_verified() -> None:
    case = _case("positive")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "VERIFIED"
    assert implementation.verdict == "VERIFIED"
    assert dict(implementation.obligation_values) == dict(oracle.obligation_values)
    assert oracle.reason_codes == ()
    assert implementation.reason_codes == ()


def test_200_and_passed_but_business_false_is_contradicted() -> None:
    case = _case("trap-200-passed-business-false")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "CONTRADICTED"
    assert implementation.verdict == "CONTRADICTED"
    # 三条弱基线都会把 200 / passed 当成恢复。
    assert run_experiments.run_baseline_any_200(case).verdict == "VERIFIED"
    assert run_experiments.run_baseline_passed_true(case).verdict == "VERIFIED"
    assert run_experiments.run_baseline_any_observation(case).verdict == "VERIFIED"


def test_stale_evidence_is_insufficient() -> None:
    case = _case("negative-stale-evidence")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == oracle.verdict
    assert "STALE" in oracle.reason_codes
    assert "STALE" in implementation.reason_codes


def test_binding_revision_mismatch_is_insufficient() -> None:
    case = _case("negative-old-binding-revision")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == oracle.verdict
    assert "WRONG_REVISION" in oracle.reason_codes
    assert "WRONG_REVISION" in implementation.reason_codes


def test_observed_revision_mismatch_is_contradicted() -> None:
    case = _case("negative-observed-revision-r16")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "CONTRADICTED"
    assert implementation.verdict == "CONTRADICTED"
    assert "WRONG_REVISION" in oracle.reason_codes
    assert "WRONG_REVISION" in implementation.reason_codes


def test_duplicate_observation_id_does_not_fill_slot() -> None:
    case = _case("negative-duplicate-observation-id")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)
    decision = _oracle_decision(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == oracle.verdict
    assert "MISSING" in oracle.reason_codes
    assert {"evidence_id": "OBS-A-2", "reason_code": "MISSING"} in decision.rejected


def test_missing_source_group_is_insufficient() -> None:
    case = _case("boundary-missing-source-group")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == oracle.verdict
    assert "MISSING" in oracle.reason_codes
    assert oracle.window_satisfied is False


def test_empty_obligations_are_rejected() -> None:
    case = _case("negative-empty-obligations")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == "INSUFFICIENT"
    assert oracle.contract_rejected is True
    assert implementation.contract_rejected is True
    assert oracle.reason_codes == ("MISSING",)


def test_ttl_closed_interval_boundary() -> None:
    accepted = _case("boundary-age-15000")
    rejected = _case("boundary-age-15001")

    assert run_experiments.run_oracle(accepted).verdict == "VERIFIED"
    assert run_experiments.run_implementation(accepted).verdict == "VERIFIED"
    assert run_experiments.run_oracle(rejected).verdict == "INSUFFICIENT"
    assert run_experiments.run_implementation(rejected).verdict == "INSUFFICIENT"


# ---------------------------------------------------------------------------
# 显式分歧案例：实现与 oracle 不在所有边界上一致
# ---------------------------------------------------------------------------

def test_multi_target_window_is_rejected() -> None:
    """回归（N08 发现 R-08）：不同 target 的来源组不得组成同一 A/B 窗口。"""
    case = _case("divergence-multi-target-window")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == "INSUFFICIENT"
    assert oracle.window_satisfied is False
    assert implementation.window_satisfied is False
    assert "MISSING" in implementation.reason_codes
    assert dict(oracle.obligation_values) == dict(implementation.obligation_values)


def test_source_conflict_converges_to_unknown() -> None:
    """单来源组内部冲突：两边均不再判 CONTRADICTED，收敛到 INSUFFICIENT。

    原因码粒度仍有差异：oracle 报 `CONFLICT`，实现因重复/冲突观测未进入采样槽而报 `MISSING`。
    """
    case = _case("negative-source-conflict")
    oracle = run_experiments.run_oracle(case)
    implementation = run_experiments.run_implementation(case)

    assert oracle.verdict == "INSUFFICIENT"
    assert implementation.verdict == "INSUFFICIENT"
    assert "CONFLICT" in oracle.reason_codes
    assert implementation.reason_codes, "UNKNOWN 必须带原因码"
    assert dict(oracle.obligation_values) == dict(implementation.obligation_values)
