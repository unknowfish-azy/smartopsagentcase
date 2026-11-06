"""VER-P0-01：有限期回执的签发、到期、失效与历史保留。"""

from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from agent.recovery_contracts import (
    EXPIRY_KIND,
    Claim,
    InvalidationEvent,
    ReceiptLedger,
    RecoveryContract,
    current_receipt,
    parse_time,
    verify,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _case(name: str) -> dict:
    return json.loads((FIXTURES / f"vp01-{name}.json").read_text(encoding="utf-8"))


def _receipt(name: str = "positive", *, receipt_id: str = "rcpt-test"):
    case = _case(name)
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
        receipt_id=receipt_id,
    )


# ---------------------------------------------------------------------------
# 签发
# ---------------------------------------------------------------------------

def test_verified_receipt_is_active_with_bounded_valid_until():
    receipt = _receipt()
    assert receipt.receipt_state == "ACTIVE"
    assert receipt.verdict == "VERIFIED"

    # valid_until = min(issued_at + receipt_ttl_ms, 最早观测 + evidence_ttl_ms)
    decision = parse_time(_case("positive")["decision_time"])
    earliest = min(
        parse_time(item["observed_at"])
        for item in _case("positive")["input"]["observations"]
    )
    assert receipt.valid_until == min(
        decision + timedelta(milliseconds=8000),
        earliest + timedelta(milliseconds=15000),
    )


def test_non_verified_receipt_is_not_issued():
    receipt = _receipt("negative-passed-but-business-false")
    assert receipt.verdict == "CONTRADICTED"
    assert receipt.receipt_state == "NOT_ISSUED"
    assert receipt.issued_at is None
    assert receipt.valid_until is None
    assert current_receipt(receipt, [], receipt.valid_until) == "NOT_ISSUED"


def test_receipt_binds_contract_claim_and_evidence_digests():
    receipt = _receipt()
    case = _case("positive")
    assert receipt.contract_digest == case["input"]["contract"]["digest"]
    assert receipt.claim_digest.startswith("sha256:")
    assert receipt.evidence_snapshot_digest.startswith("sha256:")
    assert receipt.policy_version == "recovery-eval/v1"


# ---------------------------------------------------------------------------
# 生命周期
# ---------------------------------------------------------------------------

def test_receipt_expires_at_valid_until():
    receipt = _receipt()
    assert current_receipt(receipt, [], receipt.valid_until - timedelta(milliseconds=1)) == "ACTIVE"
    assert current_receipt(receipt, [], receipt.valid_until) == "EXPIRED"


def test_expire_due_appends_event_once():
    ledger = ReceiptLedger()
    receipt = _receipt(receipt_id="rcpt-expire")
    ledger.issue(receipt)

    first = ledger.expire_due(receipt.valid_until)
    assert len(first) == 1
    assert first[0].kind == EXPIRY_KIND
    assert ledger.current(receipt.id) == "EXPIRED"

    second = ledger.expire_due(receipt.valid_until)
    assert second == []
    assert len(ledger.events(receipt.id)) == 1


def test_expire_due_skips_active_receipts():
    ledger = ReceiptLedger()
    receipt = _receipt(receipt_id="rcpt-not-due")
    ledger.issue(receipt)
    assert ledger.expire_due(receipt.valid_until - timedelta(milliseconds=1)) == []


@pytest.mark.parametrize(
    "kind", ["NEW_COUNTEREXAMPLE", "REVISION_CHANGED", "EVIDENCE_RETRACTED"]
)
def test_invalidation_events_mark_receipt_invalidated(kind: str):
    ledger = ReceiptLedger()
    receipt = _receipt(receipt_id="rcpt-invalidate")
    ledger.issue(receipt)

    event = ledger.invalidate(
        receipt.id,
        kind,
        "反例观测 obs-g3-sg-b",
        created_at=receipt.issued_at + timedelta(seconds=1),
        evidence_ids=["obs-g3-sg-b"],
    )
    assert ledger.current(receipt.id) == "INVALIDATED"
    assert ledger.events(receipt.id) == [event]


def test_invalidated_takes_priority_over_expired():
    receipt = _receipt()
    moments = receipt.valid_until + timedelta(seconds=10)
    event = InvalidationEvent(
        event_id="evt-1",
        receipt_id=receipt.id,
        kind="NEW_COUNTEREXAMPLE",
        reason="迟到反例",
        created_at=moments,
    )
    assert current_receipt(receipt, [event], moments) == "INVALIDATED"


def test_history_is_append_only_and_receipt_record_is_immutable():
    ledger = ReceiptLedger()
    receipt = _receipt(receipt_id="rcpt-history")
    ledger.issue(receipt)

    ledger.expire_due(receipt.valid_until)
    ledger.invalidate(
        receipt.id,
        "REVISION_CHANGED",
        "目标 revision 变化",
        created_at=receipt.valid_until + timedelta(seconds=5),
    )

    stored = ledger.get(receipt.id)
    assert stored.receipt_state == "ACTIVE"  # 原记录未被改写
    assert [event.kind for event in ledger.events(receipt.id)] == [
        EXPIRY_KIND,
        "REVISION_CHANGED",
    ]
    assert ledger.current(receipt.id) == "INVALIDATED"


def test_duplicate_receipt_id_is_rejected():
    ledger = ReceiptLedger()
    receipt = _receipt(receipt_id="rcpt-dup")
    ledger.issue(receipt)
    with pytest.raises(ValueError, match="禁止覆盖历史"):
        ledger.issue(receipt)


def test_unknown_event_kind_is_rejected():
    ledger = ReceiptLedger()
    receipt = _receipt(receipt_id="rcpt-bad-kind")
    ledger.issue(receipt)
    with pytest.raises(ValueError, match="失效事件类型"):
        ledger.invalidate(
            receipt.id, "CANCELLED", "x", created_at=receipt.issued_at
        )


def test_history_survives_issuance_being_disabled(tmp_path):
    """停用新签发后，仍可用同一审计文件读回历史回执与失效事件。"""
    audit = tmp_path / "receipts.jsonl"
    ledger = ReceiptLedger(path=audit)
    receipt = _receipt(receipt_id="rcpt-persisted")
    ledger.issue(receipt)
    ledger.invalidate(
        receipt.id,
        "REVISION_CHANGED",
        "目标 revision 变化",
        created_at=receipt.issued_at + timedelta(seconds=2),
    )

    reopened = ReceiptLedger(path=audit)  # 只读历史，不再签发
    assert reopened.get(receipt.id) == receipt
    assert [event.kind for event in reopened.events(receipt.id)] == ["REVISION_CHANGED"]
    assert reopened.current(receipt.id) == "INVALIDATED"
    assert reopened.receipts() == [receipt]


# ---------------------------------------------------------------------------
# 确定性：同一证据集合不得因传入顺序不同而改变摘要
# ---------------------------------------------------------------------------

def test_evidence_snapshot_digest_is_order_invariant():
    case = _case("positive")
    contract = RecoveryContract.from_dict(case["input"]["contract"])
    claim = Claim.from_dict(case["input"]["claim"])

    forward = verify(
        contract,
        claim,
        case["input"]["observations"],
        case["decision_time"],
        run_id=case["run_id"],
        verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
        receipt_id="rcpt-order-forward",
    )
    backward = verify(
        contract,
        claim,
        list(reversed(case["input"]["observations"])),
        case["decision_time"],
        run_id=case["run_id"],
        verification_round=case["verification_round"],
        authorized_scopes=[case["input"]["contract"]["scope"]],
        receipt_id="rcpt-order-backward",
    )

    assert forward.verdict == "VERIFIED"
    assert backward.verdict == "VERIFIED"
    assert forward.evidence_snapshot_digest == backward.evidence_snapshot_digest
