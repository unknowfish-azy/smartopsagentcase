"""N08 可证伪实验：独立 oracle × 被测实现 × 三个强基线。

运行：``python scripts/research/recovery_contracts/run_experiments.py``
产物：``.runtime/n08/report.json``、``.runtime/n08/summary.md``

边界：
- 不改 ``agent/recovery_contracts``，不启动平台/服务，不联网，不使用随机数。
- 案例顺序固定：先按文件名排序的 examples，再按代码里的固定顺序追加构造案例。
- 探针调用数恒为 0：本实验是冻结证据回放，不调度任何真实探针。
- 结果只陈述观测差异，不写“更优”结论。
"""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
for path in (ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from independent_oracle import (  # noqa: E402
    CONTRADICTED,
    INSUFFICIENT,
    KNOWN_PREDICATES,
    VERIFIED,
    digest_of,
    judge as oracle_judge,
    object_digest,
)

from agent.recovery_contracts import (  # noqa: E402
    Claim,
    RecoveryContract,
    evaluate,
)

EXAMPLES_DIR = ROOT / "docs" / "design" / "recovery-contract-v1" / "examples"
POSITIVE_PATH = EXAMPLES_DIR / "positive.json"
OUTPUT_DIR = ROOT / ".runtime" / "n08"
BASE_TIME = datetime(2026, 11, 5, 2, 0, 0, tzinfo=timezone.utc)
DEFAULT_GROUPS_MS = [(0, 500), (2600, 2900), (5100, 5400)]

PLACEHOLDER_PREDICATES = {
    "PRED-A-BUSINESS-SELFCHECK": ("business_health_flag", {"field": "predicate_result", "expected": True}),
    "PRED-B-TRANSACTION-PROBE": ("business_health_flag", {"field": "predicate_result", "expected": True}),
}


# ---------------------------------------------------------------------------
# 数据结构
# ---------------------------------------------------------------------------

@dataclass
class Case:
    case_id: str
    decision_time: str
    contract: dict[str, Any]
    observations: list[dict[str, Any]]
    claim: dict[str, Any] | None = None
    run_id: str | None = None
    verification_round: int | None = None
    authorized_scopes: list[str] | None = None
    expected_verdict: str | None = None
    expected_reason_codes: tuple[str, ...] = ()
    origin: str = "synthetic"
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "origin": self.origin,
            "decision_time": self.decision_time,
            "run_id": self.run_id,
            "verification_round": self.verification_round,
            "authorized_scopes": self.authorized_scopes,
            "expected_verdict": self.expected_verdict,
            "expected_reason_codes": list(self.expected_reason_codes),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class JudgeResult:
    verdict: str
    reason_codes: tuple[str, ...] = ()
    obligation_values: tuple[tuple[str, str], ...] = ()
    window_satisfied: bool | None = None
    contract_rejected: bool = False
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "obligation_values": [
                {"obligation_id": item[0], "value": item[1]} for item in self.obligation_values
            ],
            "window_satisfied": self.window_satisfied,
            "contract_rejected": self.contract_rejected,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# 公共小工具
# ---------------------------------------------------------------------------

def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


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


def _payload_object(raw: Mapping[str, Any]) -> dict[str, Any]:
    payload = raw.get("payload")
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _recompute_digests(case: Case) -> None:
    case.contract["digest"] = object_digest(case.contract)
    if case.claim is not None:
        case.claim["contract_digest"] = case.contract["digest"]
    for observation in case.observations:
        payload = observation.get("payload")
        error = observation.get("error")
        if payload is not None:
            observation["artifact_digest"] = digest_of(payload)
        elif error is not None:
            observation["artifact_digest"] = digest_of(error)


def _set_offsets(case: Case, offsets: Sequence[int], *, extra_ms: int = 5000) -> None:
    if len(offsets) != len(case.observations):
        raise ValueError(f"{case.case_id}: 时间偏移数量与观测数量不一致")
    for observation, offset in zip(case.observations, offsets):
        observation["observed_at"] = _iso(BASE_TIME + timedelta(milliseconds=offset))
    latest = max(offsets)
    case.decision_time = _iso(BASE_TIME + timedelta(milliseconds=latest + extra_ms))


def _set_times(case: Case, groups_ms: Sequence[tuple[int, int]], *, extra_ms: int = 5000) -> None:
    offsets = [item for pair in groups_ms for item in pair]
    _set_offsets(case, offsets, extra_ms=extra_ms)


def _set_decision(case: Case, offset_ms: int) -> None:
    case.decision_time = _iso(BASE_TIME + timedelta(milliseconds=offset_ms))


def _set_payloads(case: Case, factory: Callable[[Mapping[str, Any], int], dict[str, Any]]) -> None:
    for index, observation in enumerate(case.observations):
        observation["payload"] = factory(observation, index)
    _recompute_digests(case)


def _clone_positive(case_id: str, *, origin: str = "synthetic") -> Case:
    raw = json.loads(POSITIVE_PATH.read_text(encoding="utf-8"))
    case = Case(
        case_id=case_id,
        decision_time=raw["decision_time"],
        contract=copy.deepcopy(raw["input"]["contract"]),
        claim=copy.deepcopy(raw["input"].get("claim")),
        observations=copy.deepcopy(raw["input"]["observations"]),
        run_id=raw.get("run_id"),
        verification_round=raw.get("verification_round"),
        authorized_scopes=[raw["input"]["contract"]["scope"]],
        origin=origin,
    )
    _set_times(case, DEFAULT_GROUPS_MS)
    _recompute_digests(case)
    return case


def _obligation(
    obligation_id: str,
    predicate_id: str,
    params: Mapping[str, Any],
    source_groups: Sequence[str],
    collector_ids: Sequence[str],
    target: Mapping[str, Any],
    *,
    required: bool = True,
    scope: str,
    binding_revision: str,
) -> dict[str, Any]:
    return {
        "obligation_id": obligation_id,
        "predicate_id": predicate_id,
        "predicate_version": "1.0.0",
        "required": required,
        "weight": 1,
        "collector_ids": list(collector_ids),
        "source_groups": list(source_groups),
        "binding_revision": binding_revision,
        "scope": scope,
        "target": dict(target),
        "predicate_params": dict(params),
    }


# ---------------------------------------------------------------------------
# examples：读取、按样例声明的缺陷做最小可执行化
# ---------------------------------------------------------------------------

def _normalize_example(raw: Mapping[str, Any]) -> tuple[Case, list[str]]:
    case_id = raw.get("case_id") or raw.get("example_id")
    if not isinstance(case_id, str):
        raise ValueError("样例缺少 case_id/example_id")
    payload = copy.deepcopy(raw.get("input") or {})
    contract = copy.deepcopy(payload.get("contract") or {})
    observations = copy.deepcopy(payload.get("observations") or [])
    claim = copy.deepcopy(payload.get("claim"))
    notes: list[str] = []

    if case_id == "negative-missing-field":
        # 样例 defect 明确写“键缺失，不是 null”，但文件里实际是 null；
        # 按 defect 语义执行：删除键，保留 null 会变成“未报告”。
        for observation in observations:
            observation.pop("observed_revision", None)
        notes.append("按 defect 文本删除 observed_revision 键（原文件为 null，与 defect 不一致）")

    mapped = False
    for obligation in contract.get("obligations", []):
        predicate_id = obligation.get("predicate_id")
        if predicate_id not in KNOWN_PREDICATES and predicate_id in PLACEHOLDER_PREDICATES:
            new_id, params = PLACEHOLDER_PREDICATES[predicate_id]
            obligation["predicate_id"] = new_id
            obligation["predicate_params"] = dict(params)
            mapped = True
    if mapped:
        notes.append("占位谓词映射为 business_health_flag(field=predicate_result)")

    context = raw.get("context") or {}
    verification_round = raw.get("verification_round")
    if verification_round is None:
        verification_round = context.get("current_verification_round")
    run_id = raw.get("run_id")

    case = Case(
        case_id=case_id,
        decision_time=raw["decision_time"],
        contract=contract,
        observations=observations,
        claim=claim,
        run_id=run_id,
        verification_round=verification_round,
        authorized_scopes=[contract.get("scope")] if contract.get("scope") else None,
        expected_verdict=raw.get("expected_verdict"),
        expected_reason_codes=tuple(raw.get("expected_reason_codes") or ()),
        origin=f"examples/{case_id}",
        notes=tuple(notes),
    )
    _recompute_digests(case)
    return case, notes


def load_example_cases() -> list[Case]:
    cases: list[Case] = []
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        case, _ = _normalize_example(raw)
        cases.append(case)
    return cases


def build_custom_cases() -> list[Case]:
    cases: list[Case] = []

    # 1) 200 + passed=true + 业务 false：基线的典型假恢复陷阱。
    case = _clone_positive("trap-200-passed-business-false")
    case.expected_verdict = CONTRADICTED
    case.notes = ("payload 含 status_code=200、passed=true，但 business_health_flag=false",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": False},
    )
    cases.append(case)

    # 2) passed 只有声明，没有业务谓词。
    case = _clone_positive("trap-passed-only")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MALFORMED",)
    case.notes = ("payload 含 status_code=200、passed=true，但缺 recovery_status",)
    _set_payloads(case, lambda _obs, _index: {"status_code": 200, "passed": True})
    cases.append(case)

    # 3) 过期证据：形态全对，仅超过 15s TTL。
    case = _clone_positive("trap-stale-evidence")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("STALE",)
    _set_times(case, DEFAULT_GROUPS_MS, extra_ms=30000)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    cases.append(case)

    # 4) 旧 binding revision。
    case = _clone_positive("trap-old-binding-revision")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("WRONG_REVISION",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    for observation in case.observations:
        observation["binding_revision"] = "r16"
    _recompute_digests(case)
    cases.append(case)

    # 5) binding 匹配但响应版本 r16：有效反例。
    case = _clone_positive("trap-observed-revision-r16")
    case.expected_verdict = CONTRADICTED
    case.expected_reason_codes = ("WRONG_REVISION",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    for observation in case.observations:
        observation["observed_revision"] = "r16"
    _recompute_digests(case)
    cases.append(case)

    # 6) 目标不符。
    case = _clone_positive("trap-wrong-target")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("WRONG_TARGET",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    for observation in case.observations:
        observation["target"] = {
            "target_id": "service:core-db",
            "target_kind": "SERVICE",
            "endpoint": "http://127.0.0.1:18081/health",
        }
    _recompute_digests(case)
    cases.append(case)

    # 7) 跨租户 scope。
    case = _clone_positive("trap-cross-scope")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MISSING",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    for observation in case.observations:
        observation["scope"] = "tenant:t2/workspace:w9"
    _recompute_digests(case)
    cases.append(case)

    # 8) 未登记采集器身份。
    case = _clone_positive("trap-missing-collector")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MALFORMED",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    for observation in case.observations:
        observation["collector_id"] = None
    _recompute_digests(case)
    cases.append(case)

    # 9) 重复 ID：第三组 sg-a 与第一组同 ID，只剩两个不同采样。
    case = _clone_positive("trap-duplicate-observation-id")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MISSING",)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    case.observations[4]["id"] = case.observations[0]["id"]
    _recompute_digests(case)
    cases.append(case)

    # 10) 缺一个契约登记来源组。
    case = _clone_positive("boundary-missing-source-group")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MISSING",)
    case.observations = [case.observations[index] for index in (0, 2, 4)]
    _set_offsets(case, [0, 2600, 5100])
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    cases.append(case)

    # 11) 空义务 + 200 观测：契约应拒绝；200 基线会误放行。
    case = _clone_positive("boundary-empty-obligations-with-200")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MISSING",)
    case.contract["obligations"] = []
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    _recompute_digests(case)
    cases.append(case)

    # 12/13) 证据时效闭区间边界。
    for case_id, offset, verdict, codes in (
        ("boundary-age-15000", 15000, VERIFIED, ()),
        ("boundary-age-15001", 15001, INSUFFICIENT, ("STALE",)),
    ):
        case = _clone_positive(case_id)
        case.expected_verdict = verdict
        case.expected_reason_codes = tuple(codes)
        _set_payloads(
            case,
            lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
        )
        _set_decision(case, offset)
        cases.append(case)

    # 14/15) 组内偏差闭区间边界。
    for case_id, first_b, verdict, codes in (
        ("boundary-skew-1250", 1250, VERIFIED, ()),
        ("boundary-skew-1251", 1251, INSUFFICIENT, ("MISSING",)),
    ):
        case = _clone_positive(case_id)
        case.expected_verdict = verdict
        case.expected_reason_codes = tuple(codes)
        _set_payloads(
            case,
            lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
        )
        _set_times(case, [(0, first_b), (4000, 4250), (7000, 7250)])
        cases.append(case)

    # 16/17) 相邻组 group_time 间隔闭区间边界。
    for case_id, second_b, verdict, codes in (
        ("boundary-gap-4000", 4500, VERIFIED, ()),
        ("boundary-gap-4001", 4501, INSUFFICIENT, ("MISSING",)),
    ):
        case = _clone_positive(case_id)
        case.expected_verdict = verdict
        case.expected_reason_codes = tuple(codes)
        _set_payloads(
            case,
            lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
        )
        _set_times(case, [(0, 500), (4000, second_b), (8000, 8500)])
        cases.append(case)

    # 18/19) 下一组最早启动间隔闭区间边界。
    for case_id, second_a, verdict, codes in (
        ("boundary-next-gap-2000", 2540, VERIFIED, ()),
        ("boundary-next-gap-1999", 2539, INSUFFICIENT, ("MISSING",)),
    ):
        case = _clone_positive(case_id)
        case.expected_verdict = verdict
        case.expected_reason_codes = tuple(codes)
        _set_payloads(
            case,
            lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
        )
        _set_times(case, [(0, 500), (second_a, 2900), (4940, 5300)])
        cases.append(case)

    # 20) 可选义务 FALSE 不影响必需义务 VERIFIED。
    case = _clone_positive("optional-false-still-verified")
    case.expected_verdict = VERIFIED
    case.contract["obligations"].append(
        _obligation(
            "obl-instances-optional",
            "all_instances_recovered",
            {"field": "instances"},
            ["sg-a", "sg-b"],
            ["col-a", "col-b"],
            case.contract["target"],
            required=False,
            scope=case.contract["scope"],
            binding_revision=case.contract["expected_revision"],
        )
    )
    _set_payloads(
        case,
        lambda _obs, _index: {
            "recovery_status": True,
            "instances": [{"id": "i-1", "recovered": True}, {"id": "i-2", "recovered": False}],
        },
    )
    _recompute_digests(case)
    cases.append(case)

    # 21) 同 target 两个必需义务都 TRUE。
    case = _clone_positive("same-target-two-obligations")
    case.expected_verdict = VERIFIED
    case.contract["obligations"].append(
        _obligation(
            "obl-selfcheck",
            "business_health_flag",
            {"field": "passed", "expected": True},
            ["sg-a", "sg-b"],
            ["col-a", "col-b"],
            case.contract["target"],
            scope=case.contract["scope"],
            binding_revision=case.contract["expected_revision"],
        )
    )
    _set_payloads(
        case,
        lambda _obs, _index: {
            "status_code": 200,
            "passed": True,
            "recovery_status": True,
        },
    )
    _recompute_digests(case)
    cases.append(case)

    # 22) 多 target 窗口：契约 target=a，OB-B 采样 b；实现只按来源组配对窗口。
    case = _clone_positive("divergence-multi-target-window")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MISSING",)
    case.notes = (
        "契约 target=service:edge-nginx；OB-A 采集 sg-a，OB-B 采集 service:b/sg-b。",
        "semantics §4.2 要求同组 A/B 同 target；实现窗口未检查 target。",
    )
    contract = case.contract
    contract["obligations"] = [
        _obligation(
            "obl-a",
            "business_health_flag",
            {"field": "recovery_status", "expected": True},
            ["sg-a"],
            ["col-a"],
            contract["target"],
            scope=contract["scope"],
            binding_revision=contract["expected_revision"],
        ),
        _obligation(
            "obl-b",
            "business_health_flag",
            {"field": "recovery_status", "expected": True},
            ["sg-b"],
            ["col-b"],
            {"target_id": "service:b", "target_kind": "SERVICE"},
            scope=contract["scope"],
            binding_revision=contract["expected_revision"],
        ),
    ]
    _set_payloads(
        case,
        lambda _obs, _index: {
            "status_code": 200,
            "passed": True,
            "recovery_status": True,
        },
    )
    for index, observation in enumerate(case.observations):
        if observation["source_group"] == "sg-b":
            observation["target"] = {"target_id": "service:b", "target_kind": "SERVICE"}
    _set_times(case, DEFAULT_GROUPS_MS)
    _recompute_digests(case)
    cases.append(case)

    # 23) observed_revision 键真的缺失（不是 null）。
    case = _clone_positive("boundary-missing-observed-revision-key")
    case.expected_verdict = INSUFFICIENT
    case.expected_reason_codes = ("MALFORMED",)
    for observation in case.observations:
        observation.pop("observed_revision", None)
    _set_payloads(
        case,
        lambda _obs, _index: {"status_code": 200, "passed": True, "recovery_status": True},
    )
    cases.append(case)

    return cases


# ---------------------------------------------------------------------------
# 四个判定器
# ---------------------------------------------------------------------------

def run_oracle(case: Case) -> JudgeResult:
    decision = oracle_judge(
        case.contract,
        case.observations,
        case.decision_time,
        run_id=case.run_id,
        verification_round=case.verification_round,
        authorized_scopes=case.authorized_scopes,
        claim=case.claim,
    )
    return JudgeResult(
        verdict=decision.verdict,
        reason_codes=tuple(decision.reason_codes),
        obligation_values=tuple(
            (item.obligation_id, item.value) for item in decision.obligation_results
        ),
        window_satisfied=decision.window.satisfied,
        contract_rejected=decision.contract_rejected,
        error=decision.notes[0] if decision.notes else None,
    )


def run_implementation(case: Case) -> JudgeResult:
    try:
        contract = RecoveryContract.from_dict(case.contract)
        claim = Claim.from_dict(case.claim) if case.claim is not None else None
        evaluation = evaluate(
            contract,
            claim,
            case.observations,
            case.decision_time,
            run_id=case.run_id,
            verification_round=case.verification_round,
            authorized_scopes=case.authorized_scopes,
        )
    except ValueError as exc:
        # 契约/观测结构被拒绝时，V1 不得签发回执；统一按 INSUFFICIENT/MISSING 记录。
        return JudgeResult(
            verdict=INSUFFICIENT,
            reason_codes=("MISSING",),
            contract_rejected=True,
            error=str(exc),
        )
    return JudgeResult(
        verdict=evaluation.verdict,
        reason_codes=tuple(evaluation.reason_codes()),
        obligation_values=tuple(
            (item.obligation_id, item.value) for item in evaluation.obligation_results
        ),
        window_satisfied=evaluation.window.satisfied,
    )


def _has_http_200(observation: Mapping[str, Any]) -> bool:
    body = _payload_object(observation)
    status = body.get("status_code", body.get("http_status"))
    return status in (200, "200")


def _has_passed_true(observation: Mapping[str, Any]) -> bool:
    body = _payload_object(observation)
    for key in ("passed", "state_verifier_passed"):
        if _strict_bool(body.get(key)) is True:
            return True
    return False


def run_baseline_any_200(case: Case) -> JudgeResult:
    # 基线 1：任意一条观测 payload 带 HTTP 200 即恢复。
    verdict = VERIFIED if any(_has_http_200(item) for item in case.observations) else INSUFFICIENT
    return JudgeResult(verdict=verdict)


def run_baseline_passed_true(case: Case) -> JudgeResult:
    # 基线 2：任意一条观测 payload.passed=true 即恢复。
    verdict = VERIFIED if any(_has_passed_true(item) for item in case.observations) else INSUFFICIENT
    return JudgeResult(verdict=verdict)


def run_baseline_any_observation(case: Case) -> JudgeResult:
    # 基线 3：每个必需义务只要出现任意一条同来源组观测即视为满足；
    # 忽略 target、scope、round、revision、payload 值、时效和窗口。
    obligations = [
        item for item in case.contract.get("obligations", []) if item.get("required") is True
    ]
    if not obligations:
        return JudgeResult(verdict=INSUFFICIENT)
    for obligation in obligations:
        groups = set(obligation.get("source_groups") or [])
        if not any(item.get("source_group") in groups for item in case.observations):
            return JudgeResult(verdict=INSUFFICIENT)
    return JudgeResult(verdict=VERIFIED)


JUDGES: tuple[tuple[str, Callable[[Case], JudgeResult]], ...] = (
    ("independent_oracle", run_oracle),
    ("implementation", run_implementation),
    ("baseline_any_200", run_baseline_any_200),
    ("baseline_passed_true", run_baseline_passed_true),
    ("baseline_any_observation", run_baseline_any_observation),
)


# ---------------------------------------------------------------------------
# 指标与产物
# ---------------------------------------------------------------------------

def compute_metrics(
    cases: Sequence[Case],
    case_results: Mapping[str, Mapping[str, JudgeResult]],
    oracle_window_reasons: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    total = len(cases)
    metrics: dict[str, Any] = {"cases": total, "judges": {}}
    for judge_name, _ in JUDGES:
        false_verified: list[str] = []
        missed_contradicted: list[str] = []
        agreement = 0
        reason_agreement = 0
        obligation_total = 0
        obligation_agree = 0
        oracle_non_verified = 0
        oracle_contradicted = 0

        for case in cases:
            oracle = case_results[case.case_id]["independent_oracle"]
            result = case_results[case.case_id][judge_name]
            if oracle.verdict != VERIFIED:
                oracle_non_verified += 1
            if oracle.verdict == CONTRADICTED:
                oracle_contradicted += 1

            if result.verdict == VERIFIED and oracle.verdict != VERIFIED:
                false_verified.append(case.case_id)
            if oracle.verdict == CONTRADICTED and result.verdict != CONTRADICTED:
                missed_contradicted.append(case.case_id)
            if result.verdict == oracle.verdict:
                agreement += 1

            left = set(result.reason_codes)
            right = set(oracle.reason_codes)
            if judge_name == "independent_oracle":
                left.update(oracle_window_reasons.get(case.case_id, ()))
                right.update(oracle_window_reasons.get(case.case_id, ()))
            else:
                right.update(oracle_window_reasons.get(case.case_id, ()))
            if left == right:
                reason_agreement += 1

            if judge_name == "implementation":
                left_values = dict(result.obligation_values)
                right_values = dict(oracle.obligation_values)
                for obligation_id, value in right_values.items():
                    obligation_total += 1
                    if left_values.get(obligation_id) == value:
                        obligation_agree += 1

        metrics["judges"][judge_name] = {
            "false_verified": {
                "numerator": len(false_verified),
                "denominator_total": total,
                "denominator_oracle_non_verified": oracle_non_verified,
                "case_ids": false_verified,
            },
            "missed_contradicted": {
                "numerator": len(missed_contradicted),
                "denominator_oracle_contradicted": oracle_contradicted,
                "case_ids": missed_contradicted,
            },
            "agreement_with_oracle": {
                "numerator": agreement,
                "denominator": total,
            },
            "reason_code_set_agreement": {
                "numerator": reason_agreement,
                "denominator": total,
            },
            "probe_calls": {
                "numerator": 0,
                "denominator": total,
                "note": "冻结证据回放，四个判定器均不调度真实探针",
            },
        }
        if judge_name == "implementation":
            metrics["judges"][judge_name]["obligation_value_agreement"] = {
                "numerator": obligation_agree,
                "denominator": obligation_total,
            }

    oracle_label_total = 0
    oracle_label_agree = 0
    oracle_reason_total = 0
    oracle_reason_present = 0
    for case in cases:
        if case.expected_verdict is None:
            continue
        oracle = case_results[case.case_id]["independent_oracle"]
        oracle_label_total += 1
        if oracle.verdict == case.expected_verdict:
            oracle_label_agree += 1
        if case.expected_reason_codes:
            oracle_reason_total += 1
            codes = set(oracle.reason_codes)
            codes.update(oracle_window_reasons.get(case.case_id, ()))
            if set(case.expected_reason_codes).issubset(codes):
                oracle_reason_present += 1
    metrics["oracle_vs_example_or_constructed_label"] = {
        "verdict_agreement": {
            "numerator": oracle_label_agree,
            "denominator": oracle_label_total,
        },
        "expected_reason_codes_present": {
            "numerator": oracle_reason_present,
            "denominator": oracle_reason_total,
        },
    }
    return metrics


def build_report(
    cases: Sequence[Case],
    case_results: Mapping[str, Mapping[str, JudgeResult]],
    metrics: dict[str, Any],
    oracle_decisions: Mapping[str, Any],
) -> dict[str, Any]:
    case_rows: list[dict[str, Any]] = []
    for case in cases:
        row = case.to_dict()
        row["judges"] = {
            name: case_results[case.case_id][name].to_dict() for name, _ in JUDGES
        }
        oracle_decision = oracle_decisions[case.case_id]
        row["oracle"] = oracle_decision.to_dict()
        row["implementation_matches_oracle"] = (
            case_results[case.case_id]["implementation"].verdict
            == case_results[case.case_id]["independent_oracle"].verdict
            and dict(case_results[case.case_id]["implementation"].obligation_values)
            == dict(case_results[case.case_id]["independent_oracle"].obligation_values)
        )
        case_rows.append(row)

    divergences = [
        {
            "case_id": row["case_id"],
            "origin": row["origin"],
            "oracle_verdict": row["oracle"]["verdict"],
            "implementation_verdict": row["judges"]["implementation"]["verdict"],
            "oracle_obligations": row["oracle"]["obligation_results"],
            "implementation_obligations": row["judges"]["implementation"]["obligation_values"],
            "notes": row["notes"],
        }
        for row in case_rows
        if not row["implementation_matches_oracle"]
    ]

    return {
        "experiment": "n08-independent-oracle-and-strong-baselines",
        "case_count": len(cases),
        "example_case_count": sum(1 for case in cases if case.origin.startswith("examples/")),
        "constructed_case_count": sum(1 for case in cases if not case.origin.startswith("examples/")),
        "metrics": metrics,
        "divergences": divergences,
        "cases": case_rows,
        "limitations": [
            "未做真实平台/真实探针；全部为冻结证据回放，probe_calls 恒为 0。",
            "未做人为标注语料；expected_verdict 主要来自 docs 样例标签与本实验构造时的语义预期。",
            "样例 negative-missing-field 的 defect 文本称“键缺失”，但文件实际为 null；实验按 defect 文本删除键。",
            "source-conflict 的“身份未确认”只写在 context 中，V1 schema 没有承载字段；oracle 用“单来源组内冲突”作为保守代理。",
            "窗口 target 一致性按 semantics §4.2 执行；该检查由 N08 发现后补入实现（R-08），本报告为修复后复测。",
            "observed_revision=null 的语义存在“未报告=UNDETERMINED”与“不阻断业务谓词”两种解读；本实验采用前者。",
        ],
    }


def write_summary(report: Mapping[str, Any]) -> str:
    metrics = report["metrics"]["judges"]
    lines = [
        "# N08 独立 oracle × 强基线实验摘要",
        "",
        f"- 案例总数：{report['case_count']}（examples {report['example_case_count']}，构造 {report['constructed_case_count']}）",
        "- 判定器：independent_oracle、implementation、baseline_any_200、baseline_passed_true、baseline_any_observation",
        "- 探针调用：全部 0 次（冻结证据回放，不调度真实探针）",
        "",
        "## 指标（分子/分母）",
        "",
        "| 判定器 | 假 VERIFIED / 总数 | 假 VERIFIED / oracle 非 VERIFIED | 漏判 CONTRADICTED / oracle CONTRADICTED | 与 oracle 一致 | 原因码集合一致 |",
        "|---|---|---|---|---|---|",
    ]
    for name, _ in JUDGES:
        item = metrics[name]
        lines.append(
            "| {name} | {fv}/{tot} | {fv}/{nonver} | {mc}/{contra} | {ag}/{tot} | {rc}/{tot} |".format(
                name=name,
                fv=item["false_verified"]["numerator"],
                tot=item["false_verified"]["denominator_total"],
                nonver=item["false_verified"]["denominator_oracle_non_verified"],
                mc=item["missed_contradicted"]["numerator"],
                contra=item["missed_contradicted"]["denominator_oracle_contradicted"],
                ag=item["agreement_with_oracle"]["numerator"],
                rc=item["reason_code_set_agreement"]["numerator"],
            )
        )
    impl = metrics["implementation"]
    lines.extend(
        [
            "",
            f"- 实现逐义务值与 oracle 一致：{impl['obligation_value_agreement']['numerator']}/{impl['obligation_value_agreement']['denominator']}",
            f"- oracle 与样例/构造标签 verdict 一致：{report['metrics']['oracle_vs_example_or_constructed_label']['verdict_agreement']['numerator']}/{report['metrics']['oracle_vs_example_or_constructed_label']['verdict_agreement']['denominator']}",
            "",
            "## 实现与 oracle 的分歧",
            "",
        ]
    )
    if report["divergences"]:
        lines.append("| 案例 | oracle | implementation | 说明 |")
        lines.append("|---|---|---|---|")
        for item in report["divergences"]:
            lines.append(
                "| {case_id} | {oracle} | {impl} | {notes} |".format(
                    case_id=item["case_id"],
                    oracle=item["oracle_verdict"],
                    impl=item["implementation_verdict"],
                    notes="；".join(item["notes"]) or "-",
                )
            )
    else:
        lines.append("无 verdict/逐义务值分歧。")

    lines.extend(["", "## 各判定器产生假 VERIFIED 的案例", ""])
    for name, _ in JUDGES:
        ids = metrics[name]["false_verified"]["case_ids"]
        lines.append(f"- {name}：{len(ids)} 个" + (f"（{', '.join(ids)}）" if ids else ""))
    lines.extend(
        [
            "",
            "## 局限与 UNKNOWN",
            "",
        ]
    )
    for item in report["limitations"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    examples = load_example_cases()
    custom = build_custom_cases()
    cases = examples + custom

    case_results: dict[str, dict[str, JudgeResult]] = {}
    oracle_decisions: dict[str, Any] = {}
    oracle_window_reasons: dict[str, tuple[str, ...]] = {}
    for case in cases:
        results: dict[str, JudgeResult] = {}
        for name, runner in JUDGES:
            results[name] = runner(case)
        case_results[case.case_id] = results
        # 单独保留 oracle 的窗口原因，供指标补充。
        decision = oracle_judge(
            case.contract,
            case.observations,
            case.decision_time,
            run_id=case.run_id,
            verification_round=case.verification_round,
            authorized_scopes=case.authorized_scopes,
            claim=case.claim,
        )
        oracle_decisions[case.case_id] = decision
        oracle_window_reasons[case.case_id] = tuple(decision.window.reasons)

    metrics = compute_metrics(cases, case_results, oracle_window_reasons)
    report = build_report(cases, case_results, metrics, oracle_decisions)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )
    summary = write_summary(report)
    (OUTPUT_DIR / "summary.md").write_text(summary, encoding="utf-8")

    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
