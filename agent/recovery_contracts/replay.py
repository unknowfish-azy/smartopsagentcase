"""N05 同证据策略差分回放。

冻结规则来源：
- ``docs/design/recovery-contract-v1/schema.json`` 的 ``ReplayBundle``；
- ``semantics.md`` §9（``replay(bundle, policy_version)`` 返回
  ``COMPLETE | REPLAY_INCOMPLETE``，不补造未录制观测）；
- §2（变形包必须新 ``bundle_id``/``digest``/``parent_bundle_id``/``mutation_diff``
  且 ``is_historical_fact=false``，历史原包保持不变）；
- §2.1（完整性必须对照**外部受信 expected digest**，篡改原包直接拒绝）。

边界（有意如此）：
- 不访问网络、不调用模型、不读当前墙钟：判定时钟只来自
  ``bundle.decision_clock``。
- 回放结论来自冻结输入重算，不复用回放当天状态；缺录制证据时
  返回 ``REPLAY_INCOMPLETE`` 并给出缺口，不用默认值补齐。
- 回放解释证据下的决策差异，不预测未执行修复的因果效果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from .evaluator import POLICY_VERSION as SUPPORTED_POLICY_VERSION
from .models import (
    REPLAY_SCHEMA_VERSION,
    Claim,
    ContractError,
    EvidenceObservation,
    ObligationResult,
    RecoveryContract,
    VerificationReceipt,
    canonical_json,
    digest_of,
    format_time,
    object_digest,
    parse_time,
    payload_digest,
)
from .receipts import verify

REPLAY_POLICY_VERSION = REPLAY_SCHEMA_VERSION

COMPLETE = "COMPLETE"
REPLAY_INCOMPLETE = "REPLAY_INCOMPLETE"
MALFORMED = "MALFORMED"
STALE = "STALE"
REPLAY_STATES = (COMPLETE, REPLAY_INCOMPLETE, MALFORMED, STALE)

# 结构化 reason_code：回放失败必须可解释，不允许只报“失败”。
UNFROZEN_FIELD = "UNFROZEN_FIELD"
BUNDLE_DIGEST_MISMATCH = "BUNDLE_DIGEST_MISMATCH"
CONTRACT_DIGEST_MISMATCH = "CONTRACT_DIGEST_MISMATCH"
CLAIM_DIGEST_MISMATCH = "CLAIM_DIGEST_MISMATCH"
CLAIM_CONTRACT_BINDING_MISMATCH = "CLAIM_CONTRACT_BINDING_MISMATCH"
EVIDENCE_DIGEST_MISMATCH = "EVIDENCE_DIGEST_MISMATCH"
PROBE_REFERENCE_MISMATCH = "PROBE_REFERENCE_MISMATCH"
OBSERVATION_ORDER_MISMATCH = "OBSERVATION_ORDER_MISMATCH"
EXPECTED_DIGEST_MISMATCH = "EXPECTED_DIGEST_MISMATCH"
MUTATION_DIFF_INCONSISTENT = "MUTATION_DIFF_INCONSISTENT"
MALFORMED_BUNDLE = "MALFORMED_BUNDLE"
MISSING_RECORDED_PROBE = "MISSING_RECORDED_PROBE"
UNSUPPORTED_POLICY_VERSION = "UNSUPPORTED_POLICY_VERSION"

VERDICT_UNCHANGED = "VERDICT_UNCHANGED"
VERDICT_FLIPPED = "VERDICT_FLIPPED"
VALUE_CHANGED = "VALUE_CHANGED"
VALUE_UNCHANGED = "VALUE_UNCHANGED"

_BUNDLE_FIELDS = {
    "schema_version", "bundle_id", "contract", "claim", "observations",
    "source_mapping", "policy_version", "policy_config", "decision_clock",
    "observation_order", "prerecorded_probe_map", "budget", "run_event_refs",
    "dependency_versions", "digest", "parent_bundle_id", "mutation_diff",
    "is_historical_fact", "extensions",
}


class ReplayViolation(ContractError):
    """回放输入不可用；携带结构化 reason_code 与对应状态。"""

    def __init__(self, code: str, state: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code
        self.state = state


# ---------------------------------------------------------------------------
# 冻结包
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReplayBundle:
    """一次回放的冻结输入；解析即校验结构、摘要与变形不变式。"""

    bundle_id: str
    contract: RecoveryContract
    claim: Claim
    observations: tuple[EvidenceObservation, ...]
    source_mapping: dict[str, str]
    policy_version: str
    policy_config: dict[str, Any]
    decision_time: datetime
    monotonic_origin_id: str
    observation_order: tuple[str, ...]
    prerecorded_probe_map: dict[str, tuple[str, ...]]
    budget: dict[str, Any]
    run_event_refs: tuple[str, ...]
    dependency_versions: dict[str, str]
    digest: str
    parent_bundle_id: str | None
    mutation_diff: dict[str, Any] | None
    is_historical_fact: bool
    schema_version: str = REPLAY_SCHEMA_VERSION
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ReplayBundle":
        if not isinstance(raw, Mapping):
            raise ReplayViolation(MALFORMED_BUNDLE, MALFORMED, "bundle 必须是对象")
        extra = set(raw) - _BUNDLE_FIELDS
        if extra:
            # 未冻结字段不得混入冻结输入；改名塞入同样拒绝。
            raise ReplayViolation(UNFROZEN_FIELD, MALFORMED, f"未冻结字段：{sorted(extra)}")
        missing = (_BUNDLE_FIELDS - {"extensions"}) - set(raw)
        if missing:
            raise ReplayViolation(MALFORMED_BUNDLE, MALFORMED, f"缺少字段：{sorted(missing)}")

        expected = object_digest({key: value for key, value in raw.items() if key != "digest"})
        if raw.get("digest") != expected:
            raise ReplayViolation(
                BUNDLE_DIGEST_MISMATCH, MALFORMED, "bundle.digest 与 canonical 摘要不一致"
            )
        if raw.get("schema_version") != REPLAY_SCHEMA_VERSION:
            raise ReplayViolation(MALFORMED_BUNDLE, MALFORMED, "bundle.schema_version 不受支持")

        try:
            contract = RecoveryContract.from_dict(raw["contract"])
        except ContractError as exc:
            raise ReplayViolation(CONTRACT_DIGEST_MISMATCH, MALFORMED, str(exc)) from exc
        try:
            claim = Claim.from_dict(raw["claim"])
        except ContractError as exc:
            raise ReplayViolation(MALFORMED_BUNDLE, MALFORMED, str(exc)) from exc

        observations: list[EvidenceObservation] = []
        seen: set[str] = set()
        for index, item in enumerate(raw["observations"]):
            try:
                observation = EvidenceObservation.from_dict(item)
            except ContractError as exc:
                raise ReplayViolation(
                    MALFORMED_BUNDLE, MALFORMED, f"observations[{index}]：{exc}"
                ) from exc
            if observation.id in seen:
                raise ReplayViolation(
                    MALFORMED_BUNDLE, MALFORMED, f"重复观测 ID：{observation.id}"
                )
            seen.add(observation.id)
            content = (
                observation.payload if observation.payload is not None else observation.error
            )
            if observation.artifact_digest != payload_digest(content):
                # 证据摘要不符：内容已改，不得进入求值。
                raise ReplayViolation(
                    EVIDENCE_DIGEST_MISMATCH, MALFORMED, f"证据摘要不符：{observation.id}"
                )
            observations.append(observation)

        probe_map = {
            str(key): tuple(value) for key, value in dict(raw["prerecorded_probe_map"]).items()
        }
        for observation in observations:
            recorded = probe_map.get(observation.probe_id)
            if recorded is None or observation.id not in recorded:
                # 观测自称的 probe_id 与录制映射不一致：来源不可信。
                raise ReplayViolation(
                    PROBE_REFERENCE_MISMATCH, MALFORMED,
                    f"观测 {observation.id} 的 probe_id 不在录制映射",
                )

        order = tuple(raw["observation_order"])
        if len(order) != len(set(order)) or set(order) != seen:
            # 冻结顺序必须覆盖且仅覆盖全部观测；缺失时不得静默补排序冒充事实。
            raise ReplayViolation(
                OBSERVATION_ORDER_MISMATCH, MALFORMED, "observation_order 与观测集合不一致"
            )

        parent = raw.get("parent_bundle_id")
        mutation = raw.get("mutation_diff")
        is_historical = raw.get("is_historical_fact")
        if parent is None:
            if mutation is not None or is_historical is not True:
                raise ReplayViolation(
                    MUTATION_DIFF_INCONSISTENT, MALFORMED, "原历史包不得带 mutation_diff"
                )
        else:
            if mutation is None or is_historical is not False:
                raise ReplayViolation(
                    MUTATION_DIFF_INCONSISTENT, MALFORMED,
                    "变形包必须带 mutation_diff 且 is_historical_fact=false",
                )

        if claim.contract_digest != contract.digest:
            raise ReplayViolation(
                CLAIM_CONTRACT_BINDING_MISMATCH, MALFORMED, "claim 未绑定该 contract"
            )

        clock = dict(raw["decision_clock"])
        if clock.get("mode") not in ("RECORDED", "EXPLICIT"):
            raise ReplayViolation(MALFORMED_BUNDLE, MALFORMED, "decision_clock.mode 非法")

        return cls(
            bundle_id=str(raw["bundle_id"]),
            contract=contract,
            claim=claim,
            observations=tuple(observations),
            source_mapping={str(k): str(v) for k, v in dict(raw["source_mapping"]).items()},
            policy_version=str(raw["policy_version"]),
            policy_config=dict(raw["policy_config"]),
            decision_time=parse_time(clock["decision_time"]),
            monotonic_origin_id=str(clock["monotonic_origin_id"]),
            observation_order=order,
            prerecorded_probe_map=probe_map,
            budget=dict(raw["budget"]),
            run_event_refs=tuple(raw["run_event_refs"]),
            dependency_versions={str(k): str(v) for k, v in dict(raw["dependency_versions"]).items()},
            digest=str(raw["digest"]),
            parent_bundle_id=None if parent is None else str(parent),
            mutation_diff=None if mutation is None else dict(mutation),
            is_historical_fact=bool(is_historical),
            extensions=dict(raw.get("extensions") or {}),
        )


# ---------------------------------------------------------------------------
# 结果对象
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MissingProbe:
    """冻结包里没有录制结果的探针；回放不得为它补造观测。"""

    probe_id: str
    obligation_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {"probe_id": self.probe_id, "obligation_ids": list(self.obligation_ids)}


@dataclass(frozen=True)
class ObligationDiff:
    obligation_id: str
    recorded_value: str
    recomputed_value: str
    recomputed_reason_codes: tuple[str, ...]
    diff_reason_codes: tuple[str, ...]

    @property
    def changed(self) -> bool:
        return self.recorded_value != self.recomputed_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "recorded_value": self.recorded_value,
            "recomputed_value": self.recomputed_value,
            "changed": self.changed,
            "recomputed_reason_codes": list(self.recomputed_reason_codes),
            "diff_reason_codes": list(self.diff_reason_codes),
        }


@dataclass(frozen=True)
class ReplayResult:
    bundle_id: str
    replay_state: str
    reason_codes: tuple[str, ...]
    verdict: str | None
    recorded_verdict: str | None
    original_receipt_digest: str | None
    recomputed_receipt_digest: str | None
    obligation_results: tuple[ObligationResult, ...]
    obligation_diffs: tuple[ObligationDiff, ...]
    diff_reason_codes: tuple[str, ...]
    missing_probes: tuple[MissingProbe, ...]
    decision_time: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "replay_state": self.replay_state,
            "reason_codes": list(self.reason_codes),
            "verdict": self.verdict,
            "recorded_verdict": self.recorded_verdict,
            "original_receipt_digest": self.original_receipt_digest,
            "recomputed_receipt_digest": self.recomputed_receipt_digest,
            "obligation_results": [item.to_dict() for item in self.obligation_results],
            "obligation_diffs": [item.to_dict() for item in self.obligation_diffs],
            "diff_reason_codes": list(self.diff_reason_codes),
            "missing_probes": [item.to_dict() for item in self.missing_probes],
            "decision_time": self.decision_time,
        }

    def canonical(self) -> str:
        return canonical_json(self.to_dict())


def _empty_result(
    bundle_id: str,
    state: str,
    code: str,
    *,
    decision_time: str,
    recorded_verdict: str | None = None,
    original_digest: str | None = None,
    missing_probes: Sequence[MissingProbe] = (),
) -> ReplayResult:
    return ReplayResult(
        bundle_id=bundle_id,
        replay_state=state,
        reason_codes=(code,),
        verdict=None,
        recorded_verdict=recorded_verdict,
        original_receipt_digest=original_digest,
        recomputed_receipt_digest=None,
        obligation_results=(),
        obligation_diffs=(),
        diff_reason_codes=(),
        missing_probes=tuple(missing_probes),
        decision_time=decision_time,
    )


def _mutation_reasons(bundle: ReplayBundle) -> tuple[str, ...]:
    diff = bundle.mutation_diff
    if not isinstance(diff, Mapping):
        return ()
    kind = diff.get("kind")
    return (str(kind),) if isinstance(kind, str) and kind else ()


def _diff_obligations(
    contract: RecoveryContract,
    recorded: Sequence[ObligationResult],
    recomputed: Sequence[ObligationResult],
) -> tuple[ObligationDiff, ...]:
    recorded_map = {item.obligation_id: item for item in recorded}
    recomputed_map = {item.obligation_id: item for item in recomputed}
    ordered: list[str] = [item.obligation_id for item in contract.obligations]
    for obligation_id in sorted(set(recorded_map) | set(recomputed_map)):
        if obligation_id not in ordered:
            ordered.append(obligation_id)

    diffs: list[ObligationDiff] = []
    for obligation_id in ordered:
        previous = recorded_map.get(obligation_id)
        current = recomputed_map.get(obligation_id)
        previous_value = previous.value if previous is not None else "MISSING"
        current_value = current.value if current is not None else "MISSING"
        changed = previous_value != current_value
        diffs.append(
            ObligationDiff(
                obligation_id=obligation_id,
                recorded_value=previous_value,
                recomputed_value=current_value,
                recomputed_reason_codes=(
                    current.reason_codes if current is not None else ()
                ),
                diff_reason_codes=(VALUE_CHANGED if changed else VALUE_UNCHANGED,),
            )
        )
    return tuple(diffs)


# ---------------------------------------------------------------------------
# 回放
# ---------------------------------------------------------------------------

def replay(
    bundle: ReplayBundle | Mapping[str, Any],
    contract: RecoveryContract,
    claim: Claim,
    *,
    authorized_scopes: Iterable[str],
    recorded_receipt: VerificationReceipt | Mapping[str, Any] | None = None,
    required_probes: Mapping[str, Iterable[str]] | None = None,
    expected_bundle_digest: str | None = None,
) -> ReplayResult:
    """离线重算并对照录制回执；冻结输入以 bundle 为准。

    ``contract`` / ``claim`` 是调用方已解析的视图，保留在签名中以显式传入；
    回放本身严格使用 bundle 内冻结的那份，避免用外部可变对象替换冻结输入。

    ``authorized_scopes`` 与 ``verify()`` 同义（semantics §3.1/§9）：由服务端主体
    身份显式给出，回放要字节级复现录制回执就必须传入同一份授权范围。
    """
    raw = bundle.to_dict() if isinstance(bundle, ReplayBundle) else dict(bundle)
    bundle_id = str(raw.get("bundle_id", "")) if isinstance(raw, Mapping) else ""
    clock = raw.get("decision_clock") if isinstance(raw, Mapping) else None
    decision_time = (
        format_time(parse_time(clock["decision_time"]))
        if isinstance(clock, Mapping) and "decision_time" in clock
        else ""
    )

    receipt: VerificationReceipt | None = None
    if recorded_receipt is not None:
        receipt = (
            recorded_receipt
            if isinstance(recorded_receipt, VerificationReceipt)
            else VerificationReceipt.from_dict(recorded_receipt)
        )
    recorded_verdict = receipt.verdict if receipt is not None else None
    original_digest = receipt.snapshot_digest() if receipt is not None else None

    def _fail(violation: ReplayViolation) -> ReplayResult:
        return _empty_result(
            bundle_id,
            violation.state,
            violation.code,
            decision_time=decision_time,
            recorded_verdict=recorded_verdict,
            original_digest=original_digest,
        )

    try:
        parsed = ReplayBundle.from_dict(raw)
    except ReplayViolation as violation:
        return _fail(violation)

    # 外部受信 expected digest：与内部自洽摘要独立，篡改或版本不符立即拒绝。
    if expected_bundle_digest is not None:
        actual = object_digest(
            {key: value for key, value in raw.items() if key != "digest"}
        )
        if actual != expected_bundle_digest:
            return _fail(
                ReplayViolation(EXPECTED_DIGEST_MISMATCH, STALE, "与外部 expected digest 不一致")
            )

    if (
        receipt is not None
        and parsed.parent_bundle_id is None
        and digest_of(parsed.claim.to_dict()) != receipt.claim_digest
    ):
        # 原历史包必须与录制回执是同一份声明；变形包允许冻结输入不同，
        # 其差异由 mutation_diff 显式登记。
        return _fail(
            ReplayViolation(CLAIM_DIGEST_MISMATCH, STALE, "claim 摘要与录制回执不一致")
        )

    if parsed.policy_version != SUPPORTED_POLICY_VERSION:
        return _empty_result(
            parsed.bundle_id,
            REPLAY_INCOMPLETE,
            UNSUPPORTED_POLICY_VERSION,
            decision_time=format_time(parsed.decision_time),
            recorded_verdict=recorded_verdict,
            original_digest=original_digest,
        )

    if required_probes:
        missing = tuple(
            MissingProbe(
                probe_id=str(probe_id),
                obligation_ids=tuple(str(item) for item in obligation_ids),
            )
            for probe_id, obligation_ids in sorted(required_probes.items())
            if probe_id not in parsed.prerecorded_probe_map
        )
        if missing:
            # 新策略要求当前包未录制的探针：不补探、不默认 TRUE。
            return _empty_result(
                parsed.bundle_id,
                REPLAY_INCOMPLETE,
                MISSING_RECORDED_PROBE,
                decision_time=format_time(parsed.decision_time),
                recorded_verdict=recorded_verdict,
                original_digest=original_digest,
                missing_probes=missing,
            )

    if receipt is None:
        return _empty_result(
            parsed.bundle_id,
            REPLAY_INCOMPLETE,
            "NO_RECORDED_RECEIPT",
            decision_time=format_time(parsed.decision_time),
        )

    recomputed = verify(
        parsed.contract,
        parsed.claim,
        parsed.observations,
        parsed.decision_time,
        run_id=receipt.run_id,
        verification_round=receipt.verification_round,
        authorized_scopes=authorized_scopes,
        receipt_id=receipt.id,
        policy_version=parsed.policy_version,
    )

    obligation_diffs = _diff_obligations(
        parsed.contract, receipt.obligation_results, recomputed.obligation_results
    )
    verdict_changed = recomputed.verdict != receipt.verdict
    diff_reasons: list[str] = [VERDICT_FLIPPED if verdict_changed else VERDICT_UNCHANGED]
    diff_reasons.extend(_mutation_reasons(parsed))

    return ReplayResult(
        bundle_id=parsed.bundle_id,
        replay_state=COMPLETE,
        reason_codes=(),
        verdict=recomputed.verdict,
        recorded_verdict=receipt.verdict,
        original_receipt_digest=receipt.snapshot_digest(),
        recomputed_receipt_digest=recomputed.snapshot_digest(),
        obligation_results=tuple(recomputed.obligation_results),
        obligation_diffs=obligation_diffs,
        diff_reason_codes=tuple(diff_reasons),
        missing_probes=(),
        decision_time=format_time(parsed.decision_time),
    )


__all__ = [
    "BUNDLE_DIGEST_MISMATCH",
    "CLAIM_CONTRACT_BINDING_MISMATCH",
    "CLAIM_DIGEST_MISMATCH",
    "COMPLETE",
    "CONTRACT_DIGEST_MISMATCH",
    "EVIDENCE_DIGEST_MISMATCH",
    "EXPECTED_DIGEST_MISMATCH",
    "MALFORMED",
    "MALFORMED_BUNDLE",
    "MISSING_RECORDED_PROBE",
    "MUTATION_DIFF_INCONSISTENT",
    "MissingProbe",
    "OBSERVATION_ORDER_MISMATCH",
    "ObligationDiff",
    "PROBE_REFERENCE_MISMATCH",
    "REPLAY_INCOMPLETE",
    "REPLAY_POLICY_VERSION",
    "REPLAY_SCHEMA_VERSION",
    "REPLAY_STATES",
    "ReplayBundle",
    "ReplayResult",
    "ReplayViolation",
    "STALE",
    "UNFROZEN_FIELD",
    "UNSUPPORTED_POLICY_VERSION",
    "replay",
]
