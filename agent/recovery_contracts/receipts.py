"""N04 有限期回执：签发、到期、失效事件与历史保留。

冻结规则来源：``docs/design/recovery-contract-v1/semantics.md`` §7。

设计约束（有意如此，不是遗漏）：
- 本模块不接收 action / 审批 / Inspector 结果，因此结构上无法把它们当恢复证据。
  ``StateVerifier.passed`` 的真实含义保持原样（声明与观测一致），不参与 verdict。
- 历史回执不可改写；当前有效视图由 ``current_receipt(receipt, events, now)`` 计算，
  失效只追加事件。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from uuid import uuid4

from .evaluator import POLICY_VERSION, evaluate
from .models import (
    Claim,
    EvidenceObservation,
    RecoveryContract,
    VerificationReceipt,
    add_ms,
    digest_of,
    format_time,
    parse_time,
)

EXPIRY_KIND = "EXPIRED"
INVALIDATING_KINDS = ("NEW_COUNTEREXAMPLE", "REVISION_CHANGED", "EVIDENCE_RETRACTED")
EVENT_KINDS = (EXPIRY_KIND,) + INVALIDATING_KINDS


@dataclass(frozen=True)
class InvalidationEvent:
    event_id: str
    receipt_id: str
    kind: str
    reason: str
    created_at: datetime
    evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in EVENT_KINDS:
            raise ValueError(f"未知失效事件类型：{self.kind}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "receipt_id": self.receipt_id,
            "kind": self.kind,
            "reason": self.reason,
            "created_at": format_time(self.created_at),
            "evidence_ids": list(self.evidence_ids),
        }

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "InvalidationEvent":
        return cls(
            event_id=str(raw["event_id"]),
            receipt_id=str(raw["receipt_id"]),
            kind=str(raw["kind"]),
            reason=str(raw["reason"]),
            created_at=parse_time(raw["created_at"]),
            evidence_ids=tuple(raw.get("evidence_ids") or ()),
        )


def verify(
    contract: RecoveryContract,
    claim: Claim,
    observations: Iterable[EvidenceObservation | Mapping[str, Any]],
    decision_time: datetime | str,
    *,
    run_id: str,
    verification_round: int,
    authorized_scopes: Iterable[str],
    receipt_id: str | None = None,
    policy_version: str = POLICY_VERSION,
) -> VerificationReceipt:
    """只消费合格观测并生成回执记录；不执行动作、不创建审批。

    ``authorized_scopes`` 必须由服务端主体身份给出（semantics §3.1/§9），
    不接受“缺省即信任契约 scope”，避免客户端自述 scope 直接换取回执。
    """
    evaluation = evaluate(
        contract,
        claim,
        observations,
        decision_time,
        run_id=run_id,
        verification_round=verification_round,
        authorized_scopes=authorized_scopes,
    )
    decision = parse_time(decision_time)

    if evaluation.verdict == "VERIFIED":
        issued_at = decision
        valid_until = add_ms(issued_at, contract.budgets.receipt_ttl_ms)
        for observation in evaluation.used_observations:
            evidence_until = add_ms(
                observation.observed_at, contract.budgets.evidence_ttl_ms
            )
            if evidence_until < valid_until:
                valid_until = evidence_until
        receipt_state = "ACTIVE"
        snapshot = evaluation.used_observations
    else:
        # CONTRADICTED / INSUFFICIENT 一律 NOT_ISSUED，且签发时间为 null。
        issued_at = None
        valid_until = None
        receipt_state = "NOT_ISSUED"
        snapshot = evaluation.observation_snapshot

    collector_versions: dict[str, str] = {}
    for observation in snapshot:
        collector_versions.setdefault(observation.collector_id, observation.collector_version)

    revisions = {
        observation.observed_revision
        for observation in snapshot
        if observation.observed_revision is not None
    }
    observed_revision = revisions.pop() if len(revisions) == 1 else None

    return VerificationReceipt(
        id=receipt_id or f"rcpt-{uuid4().hex}",
        contract_digest=contract.digest,
        claim_digest=digest_of(claim.to_dict()),
        evidence_snapshot_digest=digest_of(
            [observation.to_dict() for observation in snapshot]
        ),
        policy_version=policy_version,
        collector_versions=dict(sorted(collector_versions.items())),
        run_id=run_id,
        verification_round=verification_round,
        target=contract.target,
        binding_revision=contract.expected_revision,
        observed_revision=observed_revision,
        obligation_results=tuple(evaluation.obligation_results),
        verdict=evaluation.verdict,
        receipt_state=receipt_state,
        issued_at=issued_at,
        valid_until=valid_until,
        invalidation_event_ids=(),
        extensions={
            # extensions 在 V1 按 UNKNOWN 处理，仅供审计阅读。
            "window": evaluation.window.to_dict(),
            "rejected_evidence": [item.to_dict() for item in evaluation.rejected],
        },
    )


def current_receipt(
    receipt: VerificationReceipt,
    events: Iterable[InvalidationEvent] = (),
    decision_time: datetime | str | None = None,
) -> str:
    """当前有效视图。优先级：INVALIDATED > EXPIRED > ACTIVE；NOT_ISSUED 不参与历史。"""
    if receipt.verdict != "VERIFIED" or receipt.receipt_state == "NOT_ISSUED":
        return "NOT_ISSUED"
    if receipt.issued_at is None or receipt.valid_until is None:
        return "NOT_ISSUED"

    related = [event for event in events if event.receipt_id == receipt.id]
    if any(event.kind in INVALIDATING_KINDS for event in related):
        return "INVALIDATED"
    if any(event.kind == EXPIRY_KIND for event in related):
        return "EXPIRED"
    if decision_time is not None:
        now = parse_time(decision_time)
        if now >= receipt.valid_until:
            return "EXPIRED"
    return "ACTIVE"


@dataclass
class ReceiptLedger:
    """只追加的失效事件账本；回执记录保持不可改写。

    ``path`` 为可选的 append-only JSONL 审计文件：签发与失效事件各写一行。
    停用新签发后，用同一个 ``path`` 重新构造账本即可读回历史审计。
    """

    path: Path | None = None
    _receipts: dict[str, VerificationReceipt] = field(default_factory=dict)
    _events: list[InvalidationEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path is not None and Path(self.path).exists():
            self._load()

    def _load(self) -> None:
        for line in Path(self.path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record["kind"] == "receipt":
                receipt = VerificationReceipt.from_dict(record["payload"])
                self._receipts[receipt.id] = receipt
            elif record["kind"] == "event":
                self._events.append(InvalidationEvent.from_dict(record["payload"]))
            else:
                raise ValueError(f"未知审计记录类型：{record['kind']}")

    def _write(self, kind: str, payload: Mapping[str, Any]) -> None:
        if self.path is None:
            return
        with Path(self.path).open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps({"kind": kind, "payload": payload}, ensure_ascii=False)
                + "\n"
            )

    def issue(self, receipt: VerificationReceipt) -> VerificationReceipt:
        if receipt.id in self._receipts:
            raise ValueError(f"回执 ID 已存在，禁止覆盖历史：{receipt.id}")
        self._receipts[receipt.id] = receipt
        self._write("receipt", receipt.to_dict())
        return receipt

    def get(self, receipt_id: str) -> VerificationReceipt:
        if receipt_id not in self._receipts:
            raise KeyError(f"未知回执：{receipt_id}")
        return self._receipts[receipt_id]

    def receipts(self) -> list[VerificationReceipt]:
        return list(self._receipts.values())

    def events(self, receipt_id: str | None = None) -> list[InvalidationEvent]:
        if receipt_id is None:
            return list(self._events)
        return [event for event in self._events if event.receipt_id == receipt_id]

    def current(self, receipt_id: str, decision_time: datetime | str | None = None) -> str:
        return current_receipt(
            self.get(receipt_id), self.events(receipt_id), decision_time
        )

    def invalidate(
        self,
        receipt_id: str,
        kind: str,
        reason: str,
        *,
        created_at: datetime | str,
        evidence_ids: Iterable[str] = (),
    ) -> InvalidationEvent:
        if kind not in INVALIDATING_KINDS:
            raise ValueError(f"失效事件类型必须是 {INVALIDATING_KINDS}")
        return self._append(receipt_id, kind, reason, created_at, evidence_ids)

    def expire_due(self, decision_time: datetime | str) -> list[InvalidationEvent]:
        """为已过 valid_until 且仍 ACTIVE 的回执追加 EXPIRED（幂等）。"""
        now = parse_time(decision_time)
        appended: list[InvalidationEvent] = []
        for receipt in self._receipts.values():
            if current_receipt(receipt, self.events(receipt.id), now) != "EXPIRED":
                continue
            if any(event.kind == EXPIRY_KIND for event in self.events(receipt.id)):
                continue
            appended.append(
                self._append(
                    receipt.id, EXPIRY_KIND, "valid_until_reached", now, ()
                )
            )
        return appended

    def _append(
        self,
        receipt_id: str,
        kind: str,
        reason: str,
        created_at: datetime | str,
        evidence_ids: Iterable[str],
    ) -> InvalidationEvent:
        self.get(receipt_id)  # 引用不存在的回执直接失败
        event = InvalidationEvent(
            event_id=f"evt-{uuid4().hex}",
            receipt_id=receipt_id,
            kind=kind,
            reason=reason,
            created_at=parse_time(created_at),
            evidence_ids=tuple(evidence_ids),
        )
        self._events.append(event)
        self._write("event", event.to_dict())
        return event
