"""N03 确定性补证调度：加权义务覆盖 + 同预算固定顺序基线。

冻结规则来源：
- ``docs/design/recovery-contract-v1/semantics.md`` §4.3（预算）、§5（补证调度、
  WAIT/STOP 与候选过滤顺序）。
- 交接书 §2.2 与 N03 卡（第 907-925 行）。

确定性约束（有意如此）：
- ``choose_next`` 是纯函数：不读墙钟、不用随机、不修改 budget；判定时间必须由
  调用方传入，调用消耗由调用方随后 ``RunBudget.record_call()`` 记账。
- 同分排序为 ``(-score, cost, probe_id)``；固定顺序基线只按 ``probe_id`` 升序。
- 不做“节省成本”结论；基线只提供同预算对照所需事件。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping

from .models import (
    ContractError,
    ObligationResult,
    RecoveryContract,
    _ms,
    add_ms,
    digest_of,
    format_time,
    parse_time,
)
from .probes import Probe, ProbeRegistry

SCHEDULER_POLICY_VERSION = "recovery-scheduler/v1"
FIXED_ORDER_POLICY_VERSION = "recovery-scheduler-fixed-order/v1"

TRUE = "TRUE"
FALSE = "FALSE"

# ProbeDecision.stop_reason 的冻结枚举。
STOP_BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
STOP_DEADLINE_EXCEEDED = "DEADLINE_EXCEEDED"
STOP_NO_COVERAGE = "NO_COVERAGE"
STOP_STATIC_INCOMPATIBLE = "STATIC_INCOMPATIBLE"
STOP_NO_NEW_INFORMATION = "NO_NEW_INFORMATION"


@dataclass
class RunBudget:
    """run 级总预算；新轮次只切换 verification_round，不重置 calls_used/deadline。"""

    run_id: str
    max_probe_calls: int
    deadline_at: datetime | str
    calls_used: int = 0
    verification_round: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.run_id, str) or not self.run_id:
            raise ContractError("run_id 必须是非空字符串")
        if isinstance(self.max_probe_calls, bool) or not isinstance(self.max_probe_calls, int):
            raise ContractError("max_probe_calls 必须是整数")
        if self.max_probe_calls < 1:
            raise ContractError("max_probe_calls 必须 >= 1")
        if isinstance(self.calls_used, bool) or not isinstance(self.calls_used, int):
            raise ContractError("calls_used 必须是整数")
        if not 0 <= self.calls_used <= self.max_probe_calls:
            raise ContractError("calls_used 必须在 0..max_probe_calls 之间")
        if isinstance(self.verification_round, bool) or not isinstance(
            self.verification_round, int
        ):
            raise ContractError("verification_round 必须是整数")
        if self.verification_round < 1:
            raise ContractError("verification_round 必须 >= 1")
        self.deadline_at = parse_time(self.deadline_at)

    @classmethod
    def from_contract(
        cls,
        contract: RecoveryContract,
        *,
        run_id: str,
        started_at: datetime | str,
        calls_used: int = 0,
        verification_round: int = 1,
    ) -> "RunBudget":
        return cls(
            run_id=run_id,
            max_probe_calls=contract.budgets.max_probe_calls,
            deadline_at=add_ms(parse_time(started_at), contract.budgets.run_deadline_ms),
            calls_used=calls_used,
            verification_round=verification_round,
        )

    @property
    def calls_remaining(self) -> int:
        return max(0, self.max_probe_calls - self.calls_used)

    def state(self, *, extra_calls: int = 0) -> dict[str, Any]:
        used = min(self.max_probe_calls, self.calls_used + max(0, extra_calls))
        return {
            "calls_used": used,
            "calls_remaining": self.max_probe_calls - used,
            "deadline_at": format_time(self.deadline_at),
        }

    def record_call(self, count: int = 1) -> None:
        """实际发起调用后记账；超预算直接拒绝，不允许静默透支。"""
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ContractError("count 必须是正整数")
        if self.calls_used + count > self.max_probe_calls:
            raise ContractError("run 级探针预算不足，禁止透支")
        self.calls_used += count

    def start_round(self, verification_round: int) -> None:
        """显式开启新核验轮次；预算与 deadline 保持不变。"""
        if isinstance(verification_round, bool) or not isinstance(verification_round, int):
            raise ContractError("verification_round 必须是整数")
        if verification_round < 1:
            raise ContractError("verification_round 必须 >= 1")
        self.verification_round = verification_round


def _normalize_results(
    results: Iterable[ObligationResult | Mapping[str, Any]],
) -> dict[str, ObligationResult]:
    mapping: dict[str, ObligationResult] = {}
    for raw in results:
        if isinstance(raw, ObligationResult):
            result = raw
        elif isinstance(raw, Mapping):
            result = ObligationResult.from_dict(raw)
        else:
            raise ContractError("results 项必须是 ObligationResult 或映射")
        if result.obligation_id in mapping:
            raise ContractError(f"results 含重复义务：{result.obligation_id}")
        mapping[result.obligation_id] = result
    return mapping


def _value_of(mapping: Mapping[str, ObligationResult], obligation_id: str) -> str | None:
    result = mapping.get(obligation_id)
    return None if result is None else result.value


def _decision_id(
    contract: RecoveryContract,
    budget: RunBudget,
    decision_time: datetime,
    policy_version: str,
    decision: str,
    selected_probe_id: str | None,
    stop_reason: str | None,
) -> str:
    """由冻结输入与选择结果派生的确定性 ID；不使用 uuid/随机数。"""
    payload = {
        "contract_digest": contract.digest,
        "decision_time": format_time(decision_time),
        "policy_version": policy_version,
        "calls_used": budget.calls_used,
        "decision": decision,
        "selected_probe_id": selected_probe_id,
        "stop_reason": stop_reason,
    }
    return "pd-" + digest_of(payload)[len("sha256:"):len("sha256:") + 16]


def _score(weight_sum: float, cost: int | float) -> float:
    # semantics §5：score(p) = 尚缺必需义务权重之和 / max(登记成本单位, 1)。
    return float(weight_sum) / max(float(cost), 1.0)


def _candidate(
    probe: Probe,
    contract: RecoveryContract,
    missing_required: Mapping[str, Any],
    budget: RunBudget,
    decision_time: datetime,
    permissions: frozenset[str] | None,
    executed_probe_ids: frozenset[str],
    exhausted_probe_ids: frozenset[str],
) -> tuple[dict[str, Any], float]:
    contract_ids = {obligation.obligation_id for obligation in contract.obligations}
    registered_coverage = [
        obligation_id for obligation_id in probe.obligation_ids
        if obligation_id in contract_ids
    ]
    accepted = [
        obligation for obligation in contract.obligations
        if obligation.obligation_id in registered_coverage
        and probe.collector_id in obligation.collector_ids
        and probe.source_group in obligation.source_groups
    ]
    missing_covered = [
        obligation for obligation in accepted
        if obligation.obligation_id in missing_required
    ]
    weight_sum = sum(float(obligation.weight) for obligation in missing_covered)
    score = _score(weight_sum, probe.cost)

    filter_reason: str | None = None
    # filter_reasons 顺序固定：UNREGISTERED → IDENTITY → SCOPE → TARGET_ALLOWLIST
    # → TOOL_PERMISSION → READ_ONLY → QUOTA → DEADLINE → COST → DUPLICATE。
    if not registered_coverage:
        filter_reason = "UNREGISTERED"
    elif not accepted:
        filter_reason = "IDENTITY"
    elif probe.target_id != contract.target.target_id:
        filter_reason = "TARGET_ALLOWLIST"
    elif permissions is not None and probe.permission not in permissions:
        filter_reason = "TOOL_PERMISSION"
    elif not probe.read_only:
        filter_reason = "READ_ONLY"
    elif budget.calls_remaining <= 0 or probe.probe_id in exhausted_probe_ids:
        filter_reason = "QUOTA"
    elif _ms(decision_time) >= _ms(budget.deadline_at):
        filter_reason = "DEADLINE"
    elif float(probe.cost) > float(budget.calls_remaining):
        filter_reason = "COST"
    elif probe.probe_id in executed_probe_ids:
        filter_reason = "DUPLICATE"
    elif not missing_covered:
        # 覆盖义务均已满足：再查不会带来新增有效信息。
        filter_reason = "DUPLICATE"

    candidate = {
        "probe_id": probe.probe_id,
        "eligible": filter_reason is None,
        "score": score,
        # schema 要求 registered_cost >= 1；实际登记成本可能小于 1，按冻结分母口径取 max。
        "registered_cost": max(float(probe.cost), 1.0),
        "covered_obligation_ids": sorted(
            obligation.obligation_id for obligation in accepted
        ),
        "filter_reasons": [] if filter_reason is None else [filter_reason],
    }
    return candidate, score


def _build_candidates(
    contract: RecoveryContract,
    missing_required: Mapping[str, Any],
    registry: ProbeRegistry,
    budget: RunBudget,
    decision_time: datetime,
    permissions: frozenset[str] | None,
    executed_probe_ids: frozenset[str],
    exhausted_probe_ids: frozenset[str],
) -> list[tuple[Probe, dict[str, Any], float]]:
    rows: list[tuple[Probe, dict[str, Any], float]] = []
    for probe in registry.probes():
        candidate, score = _candidate(
            probe,
            contract,
            missing_required,
            budget,
            decision_time,
            permissions,
            executed_probe_ids,
            exhausted_probe_ids,
        )
        rows.append((probe, candidate, score))
    return rows


def _decide(
    contract: RecoveryContract,
    results: Iterable[ObligationResult | Mapping[str, Any]],
    registry: ProbeRegistry,
    budget: RunBudget,
    decision_time: datetime | str,
    *,
    permissions: Iterable[str] | None,
    executed_probe_ids: Iterable[str],
    exhausted_probe_ids: Iterable[str],
    next_slot_at: datetime | str | None,
    required_calls_ahead: int,
    policy_version: str,
    fixed_order: bool,
) -> dict[str, Any]:
    if not isinstance(registry, ProbeRegistry):
        raise ContractError("registry 必须是 ProbeRegistry")
    if not isinstance(budget, RunBudget):
        raise ContractError("budget 必须是 RunBudget")
    if isinstance(required_calls_ahead, bool) or not isinstance(required_calls_ahead, int):
        raise ContractError("required_calls_ahead 必须是整数")
    if required_calls_ahead < 0:
        raise ContractError("required_calls_ahead 必须 >= 0")

    decision_at = parse_time(decision_time)
    result_map = _normalize_results(results)
    known_ids = {obligation.obligation_id for obligation in contract.obligations}
    unknown = set(result_map) - known_ids
    if unknown:
        raise ContractError(f"results 引用了未知义务：{sorted(unknown)}")

    required = contract.required_obligations()
    false_obligations = [
        obligation for obligation in required
        if _value_of(result_map, obligation.obligation_id) == FALSE
    ]
    missing_required = {
        obligation.obligation_id: obligation
        for obligation in required
        if _value_of(result_map, obligation.obligation_id) not in (TRUE, FALSE)
    }

    permission_set = None if permissions is None else frozenset(permissions)
    executed_set = frozenset(executed_probe_ids)
    exhausted_set = frozenset(exhausted_probe_ids)

    rows = _build_candidates(
        contract,
        missing_required,
        registry,
        budget,
        decision_at,
        permission_set,
        executed_set,
        exhausted_set,
    )
    candidates = [candidate for _, candidate, _ in rows]

    decision: str
    selected_probe_id: str | None = None
    selected_score = 0.0
    next_eligible_at: str | None = None
    stop_reason: str | None = None
    extensions: dict[str, Any] = {}

    if false_obligations:
        # 有效业务反例令本轮终止；补证不能抵消反例。
        decision = "STOP"
        stop_reason = STOP_NO_NEW_INFORMATION
        extensions["stop_detail"] = "COUNTEREXAMPLE"
        extensions["counterexample_obligation_ids"] = [
            obligation.obligation_id for obligation in false_obligations
        ]
    elif _ms(decision_at) >= _ms(budget.deadline_at):
        decision = "STOP"
        stop_reason = STOP_DEADLINE_EXCEEDED
    elif required_calls_ahead > budget.calls_remaining:
        # 静态不相容：剩余预算不足以完成已计划的采样槽。
        decision = "STOP"
        stop_reason = STOP_STATIC_INCOMPATIBLE
        extensions["required_calls_ahead"] = required_calls_ahead
        extensions["calls_remaining"] = budget.calls_remaining
    elif not missing_required:
        decision = "STOP"
        stop_reason = STOP_NO_NEW_INFORMATION
    elif budget.calls_remaining <= 0:
        decision = "STOP"
        stop_reason = STOP_BUDGET_EXHAUSTED
    elif next_slot_at is not None and _ms(parse_time(next_slot_at)) > _ms(decision_at):
        slot_time = parse_time(next_slot_at)
        if _ms(slot_time) >= _ms(budget.deadline_at):
            decision = "STOP"
            stop_reason = STOP_DEADLINE_EXCEEDED
        else:
            decision = "WAIT"
            next_eligible_at = format_time(slot_time)
    else:
        eligible_rows = [row for row in rows if row[1]["eligible"]]
        if fixed_order:
            eligible_rows.sort(key=lambda row: row[0].probe_id)
        else:
            # 同分先较低登记成本，再按 probe_id 字典序。
            eligible_rows.sort(
                key=lambda row: (-row[2], float(row[0].cost), row[0].probe_id)
            )
        if not eligible_rows:
            decision = "STOP"
            stop_reason = STOP_NO_COVERAGE
            extensions["filter_reasons"] = sorted({
                reason
                for _, candidate, _ in rows
                for reason in candidate["filter_reasons"]
            })
        else:
            probe, _, selected_score = eligible_rows[0]
            decision = "SELECTED"
            selected_probe_id = probe.probe_id

    if fixed_order:
        extensions["selection_policy"] = "FIXED_ORDER_BY_PROBE_ID"
    else:
        extensions["selection_policy"] = "WEIGHTED_COVERAGE_PER_COST"

    budget_before = budget.state()
    budget_after = budget.state(
        extra_calls=1 if decision == "SELECTED" else 0
    )

    return {
        "decision_id": _decision_id(
            contract,
            budget,
            decision_at,
            policy_version,
            decision,
            selected_probe_id,
            stop_reason,
        ),
        "policy_version": policy_version,
        "candidates": candidates,
        "score": selected_score,
        "decision": decision,
        "selected_probe_id": selected_probe_id,
        "next_eligible_at": next_eligible_at,
        "stop_reason": stop_reason,
        "budget_before": budget_before,
        "budget_after": budget_after,
        "extensions": extensions,
    }


def choose_next(
    contract: RecoveryContract,
    results: Iterable[ObligationResult | Mapping[str, Any]],
    registry: ProbeRegistry,
    budget: RunBudget,
    decision_time: datetime | str,
    *,
    permissions: Iterable[str] | None = None,
    executed_probe_ids: Iterable[str] = (),
    exhausted_probe_ids: Iterable[str] = (),
    next_slot_at: datetime | str | None = None,
    required_calls_ahead: int = 0,
) -> dict[str, Any]:
    """每次只返回一个 SELECTED / WAIT / STOP，收到结果后重新调用。"""
    return _decide(
        contract,
        results,
        registry,
        budget,
        decision_time,
        permissions=permissions,
        executed_probe_ids=executed_probe_ids,
        exhausted_probe_ids=exhausted_probe_ids,
        next_slot_at=next_slot_at,
        required_calls_ahead=required_calls_ahead,
        policy_version=SCHEDULER_POLICY_VERSION,
        fixed_order=False,
    )


def choose_next_fixed_order(
    contract: RecoveryContract,
    results: Iterable[ObligationResult | Mapping[str, Any]],
    registry: ProbeRegistry,
    budget: RunBudget,
    decision_time: datetime | str,
    *,
    permissions: Iterable[str] | None = None,
    executed_probe_ids: Iterable[str] = (),
    exhausted_probe_ids: Iterable[str] = (),
    next_slot_at: datetime | str | None = None,
    required_calls_ahead: int = 0,
) -> dict[str, Any]:
    """同预算固定顺序基线：过滤/WAIT/STOP 规则相同，仅按 probe_id 升序选择。"""
    return _decide(
        contract,
        results,
        registry,
        budget,
        decision_time,
        permissions=permissions,
        executed_probe_ids=executed_probe_ids,
        exhausted_probe_ids=exhausted_probe_ids,
        next_slot_at=next_slot_at,
        required_calls_ahead=required_calls_ahead,
        policy_version=FIXED_ORDER_POLICY_VERSION,
        fixed_order=True,
    )


def minimum_calls_for_round(
    contract: RecoveryContract,
    remaining_sample_slots: int,
) -> int:
    """V1 最小窗口的调用下界：每个剩余采样槽都要 A/B 两个来源组的观测。"""
    if isinstance(remaining_sample_slots, bool) or not isinstance(
        remaining_sample_slots, int
    ):
        raise ContractError("remaining_sample_slots 必须是整数")
    if remaining_sample_slots < 0:
        raise ContractError("remaining_sample_slots 必须 >= 0")
    return remaining_sample_slots * len(contract.source_groups)


__all__ = [
    "FALSE",
    "FIXED_ORDER_POLICY_VERSION",
    "SCHEDULER_POLICY_VERSION",
    "STOP_BUDGET_EXHAUSTED",
    "STOP_DEADLINE_EXCEEDED",
    "STOP_NO_COVERAGE",
    "STOP_NO_NEW_INFORMATION",
    "STOP_STATIC_INCOMPATIBLE",
    "TRUE",
    "RunBudget",
    "choose_next",
    "choose_next_fixed_order",
    "minimum_calls_for_round",
]
