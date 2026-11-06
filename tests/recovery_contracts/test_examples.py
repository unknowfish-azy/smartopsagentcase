"""VER-P0-01：样例包逐条验收（semantics.md §10 + 任务书反例清单）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    Claim,
    ContractError,
    RecoveryContract,
    evaluate,
    verify,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "design"
    / "recovery-contract-v1"
    / "schema.json"
)
CASE_PATHS = sorted(FIXTURES.glob("vp01-*.json"))
CASE_IDS = [path.stem.removeprefix("vp01-") for path in CASE_PATHS]


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _run(case: dict):
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])
    return verify(
        contract,
        claim,
        case["input"]["observations"],
        case["decision_time"],
        run_id=case["run_id"],
        verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
    )


def test_examples_directory_is_populated():
    # 冻结规范指向 examples/，目录为空时不得声称反例集已验证。
    assert CASE_PATHS, "examples/ 为空：样例包缺失"
    assert len(CASE_PATHS) >= 15


@pytest.mark.parametrize("path", CASE_PATHS, ids=CASE_IDS)
def test_case_matches_expected_verdict_and_reason_codes(path: Path):
    case = _load(path)
    try:
        receipt = _run(case)
    except ContractError:
        # 契约本身被拒绝（例如空义务集）：不发回执，verdict 记为 INSUFFICIENT。
        assert case["expected_verdict"] == "INSUFFICIENT"
        assert "MISSING" in case["expected_reason_codes"]
        return

    assert receipt.verdict == case["expected_verdict"]

    codes = {code for result in receipt.obligation_results for code in result.reason_codes}
    missing = set(case["expected_reason_codes"]) - codes
    assert not missing, f"期望原因码未出现：{missing}（实际 {sorted(codes)}）"


@pytest.mark.parametrize("path", CASE_PATHS, ids=CASE_IDS)
def test_receipt_state_follows_verdict(path: Path):
    case = _load(path)
    try:
        receipt = _run(case)
    except ContractError:
        return
    if receipt.verdict == "VERIFIED":
        assert receipt.receipt_state == "ACTIVE"
        assert receipt.issued_at is not None
        assert receipt.valid_until is not None
        assert receipt.valid_until > receipt.issued_at
    else:
        assert receipt.receipt_state == "NOT_ISSUED"
        assert receipt.issued_at is None
        assert receipt.valid_until is None


@pytest.mark.parametrize("path", CASE_PATHS, ids=CASE_IDS)
def test_case_declares_rule_refs_and_defect(path: Path):
    case = _load(path)
    assert case["rule_refs"], f"{path.stem} 缺 rule_refs"
    assert case["defect"], f"{path.stem} 缺 defect 说明"


def test_counterexample_acceptance_list_is_covered():
    """任务书验收反例 + semantics §10 冻结样例都必须存在。"""
    required = {
        "positive",
        "negative-stale-evidence",
        "negative-wrong-target",
        "negative-observed-revision-r16",
        "negative-old-binding-revision",
        "negative-missing-field",
        "negative-malformed-payload",
        "negative-timeout",
        "negative-source-conflict",
        "negative-different-round",
        "negative-duplicate-observation-id",
        "negative-empty-obligations",
        "negative-window-missing-sample",
        "negative-future-timestamp",
        "negative-passed-but-business-false",
        # 任务书额外要求、§10 未列的反例
        "negative-cross-scope",
        "negative-missing-collector-identity",
        "negative-partial-instance-recovery",
        "negative-single-sample-jitter",
    }
    assert required <= set(CASE_IDS), f"缺少反例：{sorted(required - set(CASE_IDS))}"


def test_positive_case_is_the_only_verified_case():
    verified = []
    for path in CASE_PATHS:
        case = _load(path)
        try:
            receipt = _run(case)
        except ContractError:
            continue
        if receipt.verdict == "VERIFIED":
            verified.append(case["case_id"])
    assert verified == ["positive"]


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def test_objects_validate_against_frozen_schema():
    jsonschema = pytest.importorskip(
        "jsonschema", reason="未安装 jsonschema：完整 Schema 校验记 SKIP，不伪装 PASS"
    )
    root = _schema()

    def subschema(definition: str) -> dict:
        return {
            "$schema": root["$schema"],
            "$id": root["$id"],
            "$defs": root["$defs"],
            "$ref": f"#/$defs/{definition}",
        }

    for path in CASE_PATHS:
        case = _load(path)
        if case["case_id"] == "negative-empty-obligations":
            # 该负例按语义必须为空义务集，因此应被 Schema 的 minItems=1 拒绝。
            with pytest.raises(jsonschema.ValidationError):
                jsonschema.validate(case["input"]["contract"], subschema("RecoveryContract"))
            continue
        for key, definition in (("contract", "RecoveryContract"), ("claim", "Claim")):
            jsonschema.validate(case["input"][key], subschema(definition))


@pytest.mark.parametrize("path", CASE_PATHS, ids=CASE_IDS)
def test_evaluate_and_verify_agree_on_verdict(path: Path):
    case = _load(path)
    try:
        contract = RecoveryContract.from_dict(case["input"]["contract"])
        claim = Claim.from_dict(case["input"]["claim"])
    except ContractError:
        return
    evaluation = evaluate(
        contract,
        claim,
        case["input"]["observations"],
        case["decision_time"],
        run_id=case["run_id"],
        verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
    )
    receipt = verify(
        contract,
        claim,
        case["input"]["observations"],
        case["decision_time"],
        run_id=case["run_id"],
        verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
        receipt_id="rcpt-fixed",
    )
    assert evaluation.verdict == receipt.verdict
    assert len(evaluation.obligation_results) == len(contract.obligations)
