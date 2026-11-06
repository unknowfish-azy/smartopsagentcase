"""N02 确定性证据义务求值器 + N04 采样窗口判定。

纯函数：不联网、不读墙钟、不写存储。判定时钟必须由调用方以
``decision_time`` 显式传入（showtime 用 UTC，internal 比较用毫秒整数）。

冻结规则来源：``docs/design/recovery-contract-v1/semantics.md``
§3（三值判定）、§4.2（采样组与窗口）、§3.5（原因码选择）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from .models import (
    Claim,
    ContractError,
    EvidenceObservation,
    ObligationResult,
    RecoveryContract,
    _ms,
    format_time,
    parse_time,
    payload_digest,
)

POLICY_VERSION = "recovery-eval/v1"

SUPPORT = "SUPPORT"
COUNTER = "COUNTER"
UNDETERMINED = "UNDETERMINED"

TRUE = "TRUE"
FALSE = "FALSE"
UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# 已审核业务谓词模板（V1 只允许登记项；LLM 自由文本不得作为谓词）
# ---------------------------------------------------------------------------

def _payload_object(observation: EvidenceObservation) -> dict[str, Any] | None:
    payload = observation.payload
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _lookup(body: Mapping[str, Any], path: str) -> Any:
    current: Any = body
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


_MISSING = object()


def _strict_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _predicate_business_health_flag(
    observation: EvidenceObservation, params: Mapping[str, Any]
) -> tuple[str, str | None]:
    body = _payload_object(observation)
    if body is None:
        return UNDETERMINED, "MALFORMED"
    path = params.get("field")
    if not isinstance(path, str) or not path:
        return UNDETERMINED, "MALFORMED"
    actual = _strict_bool(_lookup(body, path))
    if actual is None:
        return UNDETERMINED, "MALFORMED"
    expected = params.get("expected", True)
    if not isinstance(expected, bool):
        return UNDETERMINED, "MALFORMED"
    return (SUPPORT, None) if actual is expected else (COUNTER, None)


def _predicate_all_instances_recovered(
    observation: EvidenceObservation, params: Mapping[str, Any]
) -> tuple[str, str | None]:
    body = _payload_object(observation)
    if body is None:
        return UNDETERMINED, "MALFORMED"
    path = params.get("field", "instances")
    if not isinstance(path, str) or not path:
        return UNDETERMINED, "MALFORMED"
    instances = _lookup(body, path)
    if not isinstance(instances, list) or not instances:
        # 空列表不能被当成“全部实例都恢复”。
        return UNDETERMINED, "MALFORMED"
    recovered: list[bool] = []
    for item in instances:
        if not isinstance(item, Mapping):
            return UNDETERMINED, "MALFORMED"
        state = _strict_bool(item.get("recovered"))
        if state is None:
            return UNDETERMINED, "MALFORMED"
        recovered.append(state)
    return (SUPPORT, None) if all(recovered) else (COUNTER, None)


def _predicate_endpoint_reachable(
    observation: EvidenceObservation, params: Mapping[str, Any]
) -> tuple[str, str | None]:
    # 传输错误只有在本契约把它定义为业务条件时才可能判 FALSE（semantics §3.3）。
    if observation.error is None:
        return SUPPORT, None
    code = observation.error.get("code")
    if code == "TIMEOUT" and params.get("timeout_is_failure") is True:
        return COUNTER, None
    return UNDETERMINED, ("TIMEOUT" if code == "TIMEOUT" else "MALFORMED")


PREDICATE_REGISTRY = {
    "business_health_flag": _predicate_business_health_flag,
    "all_instances_recovered": _predicate_all_instances_recovered,
    "endpoint_reachable": _predicate_endpoint_reachable,
}


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObservationRejection:
    evidence_id: str
    reason_code: str

    def to_dict(self) -> dict[str, str]:
        return {"evidence_id": self.evidence_id, "reason_code": self.reason_code}


@dataclass
class WindowEvaluation:
    valid_groups: int = 0
    total_groups: int = 0
    satisfied: bool = False
    group_times: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_groups": self.valid_groups,
            "total_groups": self.total_groups,
            "satisfied": self.satisfied,
            "group_times": list(self.group_times),
            "reasons": list(self.reasons),
        }


@dataclass
class Evaluation:
    verdict: str
    obligation_results: list[ObligationResult]
    window: WindowEvaluation
    used_observations: list[EvidenceObservation]
    rejected: list[ObservationRejection]
    observation_snapshot: list[EvidenceObservation] = field(default_factory=list)
    policy_version: str = POLICY_VERSION

    def reason_codes(self) -> tuple[str, ...]:
        codes: list[str] = []
        for result in self.obligation_results:
            for code in result.reason_codes:
                if code not in codes:
                    codes.append(code)
        if self.verdict == "INSUFFICIENT" and not self.window.satisfied:
            # 窗口不满足但逐义务槽已填满时，义务结果没有原因码；缺口必须在结论层可见。
            for code in self.window.reasons:
                if code not in codes:
                    codes.append(code)
        return tuple(codes)


# ---------------------------------------------------------------------------
# 资格判定（semantics §3.1）
# ---------------------------------------------------------------------------

def _reject_reason(
    observation: EvidenceObservation,
    contract: RecoveryContract,
    obligation: Any,
    decision_time: datetime,
    run_id: str | None,
    verification_round: int | None,
    authorized_scopes: frozenset[str],
) -> str | None:
    """返回首个不合格原因码；None 表示合格。顺序对应 §3.1 的 ∧ 链。"""
    if _ms(observation.observed_at) > _ms(decision_time):
        # 未来时间不得按“负年龄”放行。
        return "MALFORMED"
    if observation.artifact_digest != payload_digest(
        observation.payload if observation.payload is not None else observation.error
    ):
        return "MALFORMED"
    if verification_round is None:
        # 调用方未声明轮次时，自述轮次的观测无法确认归属，不得当作本轮证据。
        if observation.verification_round is not None:
            return "MISSING"
    elif observation.verification_round != verification_round:
        return "MISSING"
    if run_id is None:
        # 同上：未声明 run 时，自述 run 的观测不能进入本 run 的证据集。
        if observation.run_id is not None:
            return "STALE"
    elif observation.run_id != run_id:
        return "STALE"
    if observation.scope not in authorized_scopes:
        return "MISSING"
    if observation.target.target_id != obligation.target.target_id:
        return "WRONG_TARGET"
    if observation.collector_id not in obligation.collector_ids:
        # 未登记采集器不是合格观测源（身份不由 URL 或自述推断）。
        return "MALFORMED"
    if observation.source_group not in obligation.source_groups:
        return "MALFORMED"
    if observation.binding_revision != contract.expected_revision:
        return "WRONG_REVISION"
    if _ms(decision_time) - _ms(observation.observed_at) > contract.budgets.evidence_ttl_ms:
        return "STALE"
    return None


def _observation_value(
    observation: EvidenceObservation,
    contract: RecoveryContract,
    obligation: Any,
) -> tuple[str, str | None]:
    """把一条合格观测映射到 SUPPORT / COUNTER / UNDETERMINED。"""
    if observation.error is not None:
        code = observation.error.get("code")
        if code == "TIMEOUT":
            # 超时默认是“采集不足”，不是业务失败；只有契约把它定义为业务条件时才判 FALSE。
            if (
                obligation.predicate_id == "endpoint_reachable"
                and obligation.predicate_params.get("timeout_is_failure") is True
            ):
                return COUNTER, None
            return UNDETERMINED, "TIMEOUT"
        return UNDETERMINED, "MALFORMED"
    # binding_revision 已匹配但响应 observed_revision 明确不同：有效版本反例。
    if observation.observed_revision is None:
        return UNDETERMINED, "MISSING"
    if observation.observed_revision != contract.expected_revision:
        return COUNTER, "WRONG_REVISION"
    return PREDICATE_REGISTRY[obligation.predicate_id](
        observation, obligation.predicate_params
    )


def _ordered(
    observations: Iterable[EvidenceObservation],
) -> list[EvidenceObservation]:
    return sorted(
        observations,
        key=lambda item: (_ms(item.observed_at), item.sequence, item.id),
    )


def _by_source_group(
    observations: Sequence[EvidenceObservation],
) -> dict[str, list[EvidenceObservation]]:
    groups: dict[str, list[EvidenceObservation]] = {}
    for observation in observations:
        groups.setdefault(observation.source_group, []).append(observation)
    return {key: _ordered(value) for key, value in groups.items()}


# ---------------------------------------------------------------------------
# 采样窗口（semantics §4.2）
# ---------------------------------------------------------------------------

def evaluate_window(
    contract: RecoveryContract,
    eligible: Sequence[EvidenceObservation],
) -> WindowEvaluation:
    grouped = _by_source_group(eligible)
    if not all(group in grouped for group in contract.source_groups):
        return WindowEvaluation(total_groups=0, satisfied=False, reasons=["MISSING"])

    total = min(len(grouped[group]) for group in contract.source_groups)
    window = contract.window
    valid: list[tuple[datetime, list[EvidenceObservation]]] = []

    for index in range(total):
        members = [grouped[group][index] for group in contract.source_groups]
        if len({item.target.target_id for item in members}) != 1:
            continue  # 同一采样组必须共享同一 target（semantics §4.2）
        times = [_ms(item.observed_at) for item in members]
        skew = max(times) - min(times)
        if skew > window.max_intra_group_skew_ms:
            continue  # 组内偏差越界 → 该组无效
        valid.append((max(members, key=lambda item: item.observed_at).observed_at, members))

    result = WindowEvaluation(
        valid_groups=len(valid),
        total_groups=total,
        group_times=[format_time(moment) for moment, _ in valid],
    )

    if len(valid) < window.sample_groups:
        result.reasons.append("MISSING")

    gaps_ok = True
    for previous, current in zip(valid, valid[1:]):
        previous_time, _ = previous
        _, members = current
        gap = _ms(current[0]) - _ms(previous_time)
        if gap > window.max_adjacent_gap_ms:
            gaps_ok = False
        earliest_start = min(
            _ms(item.observed_at) - item.elapsed_ms for item in members
        )
        # 下一组最早启动不得早于前组组时间 + 2000ms（计划时间不算事实）。
        if earliest_start < _ms(previous_time) + window.min_next_group_gap_ms:
            gaps_ok = False

    if valid:
        span = _ms(valid[-1][0]) - _ms(valid[0][0])
        if span < window.min_first_last_gap_ms:
            gaps_ok = False

    if not gaps_ok:
        result.reasons.append("MISSING")

    result.reasons = list(dict.fromkeys(result.reasons))
    result.satisfied = (
        len(valid) >= window.sample_groups and gaps_ok and not result.reasons
    )
    return result


# ---------------------------------------------------------------------------
# 义务求值
# ---------------------------------------------------------------------------

def _obligation_result(
    contract: RecoveryContract,
    obligation: Any,
    observations: Sequence[EvidenceObservation],
    rejections: dict[str, str],
    decision_time: datetime,
    parse_failure_codes: Sequence[str] = (),
) -> tuple[ObligationResult, set[str]]:
    relevant = [item for item in observations if item.source_group in obligation.source_groups]
    grouped = _by_source_group(relevant)
    sample_slots = contract.window.sample_groups

    counters: list[EvidenceObservation] = []
    counter_codes: list[str] = []
    slot_evidence: set[str] = set()
    unfilled_slots = 0
    undetermined_codes: set[str] = set()
    conflict = False

    eligible_support = False
    ineligible_counter = False

    for observation in relevant:
        reason = rejections.get(observation.id)
        if reason is None:
            value, code = _observation_value(observation, contract, obligation)
            if value == COUNTER:
                counters.append(observation)
                if code:
                    counter_codes.append(code)
            elif value == UNDETERMINED:
                if code:
                    undetermined_codes.add(code)
            elif value == SUPPORT:
                eligible_support = True
        else:
            raw_value, _ = _observation_value(observation, contract, obligation)
            if raw_value == COUNTER:
                # 身份/来源未确认的矛盾只构成 UNKNOWN，不判 FALSE。
                ineligible_counter = True

    for index in range(sample_slots):
        for source_group in obligation.source_groups:
            members = grouped.get(source_group, [])
            observation = members[index] if index < len(members) else None
            if observation is None:
                unfilled_slots += 1
                continue
            if rejections.get(observation.id) is not None:
                unfilled_slots += 1
                continue
            value, _ = _observation_value(observation, contract, obligation)
            if value != SUPPORT:
                unfilled_slots += 1
                continue
            slot_evidence.add(observation.id)

    if counters:
        # 不得用多数投票消除业务失败证据。
        used = tuple(sorted({item.id for item in counters}))
        rejected = tuple(
            ObservationRejection(
                evidence_id=item.id,
                reason_code=rejections[item.id],
            ).to_dict()
            for item in relevant
            if item.id in rejections
        )
        return (
            ObligationResult(
                obligation_id=obligation.obligation_id,
                value=FALSE,
                reason_codes=tuple(dict.fromkeys(counter_codes)),
                used_evidence_ids=used,
                rejected_evidence=rejected,
                checked_at=decision_time,
            ),
            slot_evidence,
        )

    used_ids = tuple(sorted(slot_evidence))
    if eligible_support and ineligible_counter:
        # 身份/来源未确认的矛盾不得被已填满的 TRUE 槽掩盖（semantics §3.3）。
        conflict = True
    if unfilled_slots == 0 and used_ids and not conflict:
        return (
            ObligationResult(
                obligation_id=obligation.obligation_id,
                value=TRUE,
                reason_codes=(),
                used_evidence_ids=used_ids,
                rejected_evidence=tuple(
                    ObservationRejection(item.id, rejections[item.id]).to_dict()
                    for item in relevant
                    if item.id in rejections
                ),
                checked_at=decision_time,
            ),
            slot_evidence,
        )

    codes: list[str] = []
    # 结构上无法解析的观测进不了本义务的 relevant 集合，但其 MALFORMED 必须可见。
    codes.extend(parse_failure_codes)
    for observation in relevant:
        reason = rejections.get(observation.id)
        if reason is not None:
            codes.append(reason)
        else:
            value, code = _observation_value(observation, contract, obligation)
            if value == UNDETERMINED and code:
                codes.append(code)
    if conflict:
        codes.append("CONFLICT")
    if unfilled_slots:
        # 采样槽未填满/证据属于其他轮次/无合格观测 → MISSING。
        codes.append("MISSING")
    if not codes:
        codes.append("MISSING")

    return (
        ObligationResult(
            obligation_id=obligation.obligation_id,
            value=UNKNOWN,
            reason_codes=tuple(dict.fromkeys(codes)),
            used_evidence_ids=(),
            rejected_evidence=tuple(
                ObservationRejection(item.id, rejections[item.id]).to_dict()
                for item in relevant
                if item.id in rejections
            ),
            checked_at=decision_time,
        ),
        slot_evidence,
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def evaluate(
    contract: RecoveryContract,
    claim: Claim | None,
    observations: Iterable[EvidenceObservation | Mapping[str, Any]],
    decision_time: datetime | str,
    *,
    run_id: str | None = None,
    verification_round: int | None = None,
    authorized_scopes: Iterable[str] | None = None,
) -> Evaluation:
    """对契约求值，返回逐义务结果 + 窗口。claim 只用于声明与契约的摘要绑定。"""
    if claim is not None and claim.contract_digest != contract.digest:
        raise ContractError("claim.contract_digest 与 contract.digest 不一致")
    if not contract.required_obligations():
        # 没有可计算义务的契约不能签发任何回执。
        raise ContractError("契约没有 required 义务")

    for obligation in contract.obligations:
        if obligation.predicate_id not in PREDICATE_REGISTRY:
            raise ContractError(
                f"未登记的已审核谓词：{obligation.predicate_id}"
            )

    decision = parse_time(decision_time)
    scopes = frozenset(authorized_scopes) if authorized_scopes is not None else frozenset(
        {contract.scope}
    )

    parsed: list[EvidenceObservation] = []
    rejected: list[ObservationRejection] = []
    parse_failure_codes: list[str] = []

    items = list(observations)
    id_counts: dict[str, int] = {}
    for raw in items:
        identifier = (
            raw.id
            if isinstance(raw, EvidenceObservation)
            else raw.get("id") if isinstance(raw, Mapping) else None
        )
        if isinstance(identifier, str) and identifier:
            id_counts[identifier] = id_counts.get(identifier, 0) + 1

    for raw in items:
        if isinstance(raw, EvidenceObservation):
            observation = raw
        else:
            try:
                observation = EvidenceObservation.from_dict(raw)
            except ContractError:
                evidence_id = raw.get("id") if isinstance(raw, Mapping) else None
                parse_failure_codes.append("MALFORMED")
                if isinstance(evidence_id, str) and evidence_id:
                    rejected.append(ObservationRejection(evidence_id, "MALFORMED"))
                continue
        if id_counts.get(observation.id, 0) > 1:
            # 重复 ID 的语义有歧义：所有副本都不填补采样槽，避免先到先得改变判定。
            rejected.append(ObservationRejection(observation.id, "MISSING"))
            continue
        parsed.append(observation)

    # 资格是逐义务判定的：同一观测可能对该义务合格、对另一义务不合格。
    rejections_by_obligation: dict[str, dict[str, str]] = {}
    for obligation in contract.obligations:
        mapping: dict[str, str] = {}
        for observation in parsed:
            reason = _reject_reason(
                observation, contract, obligation, decision, run_id,
                verification_round, scopes,
            )
            if reason is not None:
                mapping[observation.id] = reason
        rejections_by_obligation[obligation.obligation_id] = mapping

    results: list[ObligationResult] = []
    used_ids: set[str] = set()
    for obligation in contract.obligations:
        result, slots = _obligation_result(
            contract, obligation, parsed,
            rejections_by_obligation[obligation.obligation_id], decision,
            parse_failure_codes,
        )
        results.append(result)
        if obligation.required and result.value == TRUE:
            used_ids.update(slots)

    # 窗口使用“至少对一个义务合格”的观测；单个义务缺槽仍会导致该义务 UNKNOWN。
    eligible = [
        item for item in parsed
        if any(
            item.id not in mapping for mapping in rejections_by_obligation.values()
        )
    ]
    window_eval = evaluate_window(contract, eligible)

    required_values = [
        result.value
        for obligation, result in zip(contract.obligations, results)
        if obligation.required
    ]
    if any(value == FALSE for value in required_values):
        verdict = "CONTRADICTED"
    elif all(value == TRUE for value in required_values) and window_eval.satisfied:
        verdict = "VERIFIED"
    else:
        verdict = "INSUFFICIENT"

    seen_rejections: set[tuple[str, str]] = set()
    all_rejections: list[ObservationRejection] = []
    for mapping in rejections_by_obligation.values():
        for evidence_id, code in mapping.items():
            if (evidence_id, code) in seen_rejections:
                continue
            seen_rejections.add((evidence_id, code))
            all_rejections.append(ObservationRejection(evidence_id, code))

    return Evaluation(
        verdict=verdict,
        obligation_results=results,
        window=window_eval,
        used_observations=_ordered([item for item in parsed if item.id in used_ids]),
        rejected=rejected + all_rejections,
        observation_snapshot=_ordered(parsed),
    )
