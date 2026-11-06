"""recovery-contract/v1 七对象的消费者实现（schema owner = N01）。

本模块只做读取/写出行必需的最小校验：字段存在性、类型、枚举、冻结常量、
canonical JSON 与 digest。完整 JSON Schema 校验由 `tests/recovery_contracts`
在安装 `jsonschema` 时额外比对；未安装时该用例记 SKIP，不伪装 PASS。

冻结来源：``docs/design/recovery-contract-v1/schema.json`` 与 ``semantics.md``。
任何字段/枚举/阈值变更须先走 N01 版本化修订，本模块不得自行放宽或改名。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

SCHEMA_VERSION = "recovery-contract/v1"
REPLAY_SCHEMA_VERSION = "recovery-replay/v1"

REASON_CODES = (
    "MISSING",
    "STALE",
    "WRONG_TARGET",
    "WRONG_REVISION",
    "CONFLICT",
    "TIMEOUT",
    "MALFORMED",
)
EVIDENCE_VALUES = ("TRUE", "FALSE", "UNKNOWN")
VERDICTS = ("VERIFIED", "CONTRADICTED", "INSUFFICIENT")
RECEIPT_STATES = ("NOT_ISSUED", "ACTIVE", "INVALIDATED", "EXPIRED")
TARGET_KINDS = ("SERVICE", "PROCESS", "ENDPOINT")

# semantics.md §4.2 / §4.3 冻结的窗口与预算常量。
WINDOW_CONSTANTS = {
    "sample_groups": 3,
    "min_first_last_gap_ms": 4000,
    "max_adjacent_gap_ms": 4000,
    "max_intra_group_skew_ms": 1250,
    "min_next_group_gap_ms": 2000,
}
BUDGET_CONSTANTS = {
    "max_probe_calls": 12,
    "per_probe_timeout_ms": 1000,
    "run_deadline_ms": 30000,
    "evidence_ttl_ms": 15000,
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")


class ContractError(ValueError):
    """对象不满足 recovery-contract/v1 的冻结约束。"""


# ---------------------------------------------------------------------------
# canonical JSON / digest / time
# ---------------------------------------------------------------------------

def canonical_json(value: Any) -> str:
    """UTF-8 canonical JSON：键按码位升序、无空白、禁止 NaN/Infinity。"""
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def digest_of(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def object_digest(mapping: Mapping[str, Any]) -> str:
    """删除对象自身 digest 字段后做 canonical 摘要。"""
    return digest_of({key: value for key, value in mapping.items() if key != "digest"})


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:  # 非法时间按结构错误处理
            raise ContractError(f"非法 date-time：{value!r}") from exc
    else:
        raise ContractError(f"需要 date-time，得到 {value!r}")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_time(value: Any) -> str:
    return parse_time(value).isoformat().replace("+00:00", "Z")


def _ms(moment: datetime) -> int:
    """毫秒级整数时间，避免浮点比较误差。"""
    return int(moment.timestamp() * 1000)


def add_ms(moment: datetime, milliseconds: int) -> datetime:
    return moment + timedelta(milliseconds=milliseconds)


# ---------------------------------------------------------------------------
# 校验辅助
# ---------------------------------------------------------------------------

def _strict(mapping: Mapping[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(mapping) - allowed
    if unknown:
        raise ContractError(f"{where} 含未冻结字段：{sorted(unknown)}")


def _mapping(value: Any, where: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{where} 必须是对象")
    return value


def _text(mapping: Mapping[str, Any], key: str, where: str, *, pattern=None) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ContractError(f"{where}.{key} 必须是非空字符串")
    if pattern is not None and not pattern.fullmatch(value):
        raise ContractError(f"{where}.{key} 不符合模式：{value!r}")
    return value


def _ident(mapping: Mapping[str, Any], key: str, where: str) -> str:
    return _text(mapping, key, where, pattern=_ID_RE)


def _digest(mapping: Mapping[str, Any], key: str, where: str) -> str:
    return _text(mapping, key, where, pattern=_DIGEST_RE)


def _flag(mapping: Mapping[str, Any], key: str, where: str) -> bool:
    value = mapping.get(key)
    if not isinstance(value, bool):
        raise ContractError(f"{where}.{key} 必须是布尔值")
    return value


def _integer(mapping: Mapping[str, Any], key: str, where: str, *, minimum: int | None = None,
             maximum: int | None = None) -> int:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{where}.{key} 必须是整数")
    if minimum is not None and value < minimum:
        raise ContractError(f"{where}.{key} 必须 >= {minimum}")
    if maximum is not None and value > maximum:
        raise ContractError(f"{where}.{key} 必须 <= {maximum}")
    return value


def _number(mapping: Mapping[str, Any], key: str, where: str) -> int | float:
    value = mapping.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{where}.{key} 必须是数值")
    if value <= 0:
        raise ContractError(f"{where}.{key} 必须 > 0")
    return value


def _id_list(mapping: Mapping[str, Any], key: str, where: str, *, minimum: int) -> tuple[str, ...]:
    value = mapping.get(key)
    if not isinstance(value, list) or len(value) < minimum:
        raise ContractError(f"{where}.{key} 至少 {minimum} 项")
    items: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not _ID_RE.fullmatch(item):
            raise ContractError(f"{where}.{key}[{index}] 不是合法标识")
        items.append(item)
    if len(set(items)) != len(items):
        raise ContractError(f"{where}.{key} 含重复项")
    return tuple(items)


# ---------------------------------------------------------------------------
# Target / Window / Budgets / Obligation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    target_id: str
    target_kind: str
    endpoint: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], where: str = "target") -> "Target":
        raw = _mapping(raw, where)
        _strict(raw, {"target_id", "target_kind", "endpoint"}, where)
        target_id = _text(raw, "target_id", where)
        if len(target_id) > 256:
            raise ContractError(f"{where}.target_id 超过 256 字符")
        kind = raw.get("target_kind")
        if kind not in TARGET_KINDS:
            raise ContractError(f"{where}.target_kind 必须是 {TARGET_KINDS}")
        endpoint = raw.get("endpoint")
        if endpoint is not None and (not isinstance(endpoint, str) or not endpoint):
            raise ContractError(f"{where}.endpoint 必须是字符串或 null")
        return cls(target_id=target_id, target_kind=kind, endpoint=endpoint)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {"target_id": self.target_id, "target_kind": self.target_kind}
        if self.endpoint is not None:
            body["endpoint"] = self.endpoint
        return body


@dataclass(frozen=True)
class Window:
    sample_groups: int = 3
    min_first_last_gap_ms: int = 4000
    max_adjacent_gap_ms: int = 4000
    max_intra_group_skew_ms: int = 1250
    min_next_group_gap_ms: int = 2000

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], where: str = "window") -> "Window":
        raw = _mapping(raw, where)
        _strict(raw, set(WINDOW_CONSTANTS), where)
        for key, expected in WINDOW_CONSTANTS.items():
            actual = _integer(raw, key, where)
            if actual != expected:
                raise ContractError(f"{where}.{key} 冻结为 {expected}，得到 {actual}")
        return cls()

    def to_dict(self) -> dict[str, int]:
        return dict(WINDOW_CONSTANTS)


@dataclass(frozen=True)
class Budgets:
    max_probe_calls: int = 12
    per_probe_timeout_ms: int = 1000
    run_deadline_ms: int = 30000
    evidence_ttl_ms: int = 15000
    receipt_ttl_ms: int = 8000

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], where: str = "budgets") -> "Budgets":
        raw = _mapping(raw, where)
        _strict(raw, {"max_probe_calls", "per_probe_timeout_ms", "run_deadline_ms",
                      "evidence_ttl_ms", "receipt_ttl_ms"}, where)
        for key, expected in BUDGET_CONSTANTS.items():
            actual = _integer(raw, key, where)
            if actual != expected:
                raise ContractError(f"{where}.{key} 冻结为 {expected}，得到 {actual}")
        receipt_ttl = _integer(raw, "receipt_ttl_ms", where, minimum=1000)
        return cls(receipt_ttl_ms=receipt_ttl)

    def to_dict(self) -> dict[str, int]:
        return {
            "max_probe_calls": self.max_probe_calls,
            "per_probe_timeout_ms": self.per_probe_timeout_ms,
            "run_deadline_ms": self.run_deadline_ms,
            "evidence_ttl_ms": self.evidence_ttl_ms,
            "receipt_ttl_ms": self.receipt_ttl_ms,
        }


@dataclass(frozen=True)
class Obligation:
    obligation_id: str
    predicate_id: str
    predicate_version: str
    required: bool
    weight: int | float
    collector_ids: tuple[str, ...]
    source_groups: tuple[str, ...]
    binding_revision: str
    scope: str
    target: Target
    predicate_params: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any], where: str = "obligation") -> "Obligation":
        raw = _mapping(raw, where)
        _strict(raw, {
            "obligation_id", "predicate_id", "predicate_version", "required", "weight",
            "collector_ids", "source_groups", "binding_revision", "scope", "target",
            "predicate_params", "extensions",
        }, where)
        params = raw.get("predicate_params", {})
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            raise ContractError(f"{where}.predicate_params 必须是对象")
        return cls(
            obligation_id=_ident(raw, "obligation_id", where),
            predicate_id=_text(raw, "predicate_id", where, pattern=_ID_RE),
            predicate_version=_text(raw, "predicate_version", where),
            required=_flag(raw, "required", where),
            weight=_number(raw, "weight", where),
            collector_ids=_id_list(raw, "collector_ids", where, minimum=1),
            source_groups=_id_list(raw, "source_groups", where, minimum=1),
            binding_revision=_text(raw, "binding_revision", where),
            scope=_text(raw, "scope", where),
            target=Target.from_dict(_mapping(raw.get("target"), f"{where}.target"),
                                    f"{where}.target"),
            predicate_params=dict(params),
        )

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "obligation_id": self.obligation_id,
            "predicate_id": self.predicate_id,
            "predicate_version": self.predicate_version,
            "required": self.required,
            "weight": self.weight,
            "collector_ids": list(self.collector_ids),
            "source_groups": list(self.source_groups),
            "binding_revision": self.binding_revision,
            "scope": self.scope,
            "target": self.target.to_dict(),
        }
        if self.predicate_params:
            body["predicate_params"] = dict(self.predicate_params)
        return body


# ---------------------------------------------------------------------------
# RecoveryContract
# ---------------------------------------------------------------------------

_CONTRACT_FIELDS = {
    "schema_version", "id", "version", "scope", "target", "expected_revision",
    "template_id", "template_version", "obligations", "source_groups", "window",
    "budgets", "expires_after", "digest", "extensions",
}


@dataclass(frozen=True)
class RecoveryContract:
    id: str
    version: str
    scope: str
    target: Target
    expected_revision: str
    template_id: str
    template_version: str
    obligations: tuple[Obligation, ...]
    source_groups: tuple[str, ...]
    window: Window
    budgets: Budgets
    expires_after: int
    digest: str = ""
    schema_version: str = SCHEMA_VERSION
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "RecoveryContract":
        raw = _mapping(raw, "contract")
        _strict(raw, _CONTRACT_FIELDS, "contract")
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ContractError(f"contract.schema_version 必须是 {SCHEMA_VERSION}")
        obligation_raw = raw.get("obligations")
        if not isinstance(obligation_raw, list) or not obligation_raw:
            # semantics.md §2：空义务集必须被拒绝，没有可计算义务就不能签发回执。
            raise ContractError("contract.obligations 至少 1 项")
        obligations = tuple(
            Obligation.from_dict(item, f"contract.obligations[{index}]")
            for index, item in enumerate(obligation_raw)
        )
        contract = cls(
            id=_ident(raw, "id", "contract"),
            version=_text(raw, "version", "contract"),
            scope=_text(raw, "scope", "contract"),
            target=Target.from_dict(_mapping(raw.get("target"), "contract.target"),
                                    "contract.target"),
            expected_revision=_text(raw, "expected_revision", "contract"),
            template_id=_text(raw, "template_id", "contract"),
            template_version=_text(raw, "template_version", "contract"),
            obligations=obligations,
            source_groups=_id_list(raw, "source_groups", "contract", minimum=2),
            window=Window.from_dict(_mapping(raw.get("window"), "contract.window"),
                                    "contract.window"),
            budgets=Budgets.from_dict(_mapping(raw.get("budgets"), "contract.budgets"),
                                      "contract.budgets"),
            expires_after=_integer(raw, "expires_after", "contract", minimum=1000),
            digest=_digest(raw, "digest", "contract"),
            extensions=dict(raw.get("extensions") or {}),
        )
        if contract.digest != object_digest(raw):
            # 冻结历史被改动即拒绝，不做“边声称拒绝篡改、边继续求值”。
            raise ContractError("contract.digest 与 canonical 摘要不一致")
        return contract

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "version": self.version,
            "scope": self.scope,
            "target": self.target.to_dict(),
            "expected_revision": self.expected_revision,
            "template_id": self.template_id,
            "template_version": self.template_version,
            "obligations": [item.to_dict() for item in self.obligations],
            "source_groups": list(self.source_groups),
            "window": self.window.to_dict(),
            "budgets": self.budgets.to_dict(),
            "expires_after": self.expires_after,
        }
        if self.extensions:
            body["extensions"] = dict(self.extensions)
        body["digest"] = object_digest(body)
        return body

    def required_obligations(self) -> tuple[Obligation, ...]:
        return tuple(item for item in self.obligations if item.required)


# ---------------------------------------------------------------------------
# Claim
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Claim:
    id: str
    contract_digest: str
    scope: str
    target: Target
    expected_revision: str
    claim_type: str = "BUSINESS_RECOVERY"
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Claim":
        raw = _mapping(raw, "claim")
        _strict(raw, {"id", "contract_digest", "scope", "target", "expected_revision",
                      "claim_type", "extensions"}, "claim")
        claim_type = raw.get("claim_type")
        if claim_type != "BUSINESS_RECOVERY":
            # V1 只批准结构化业务恢复声明；自然语言结论只能作为候选 Claim。
            raise ContractError("claim.claim_type 在 V1 只能是 BUSINESS_RECOVERY")
        return cls(
            id=_ident(raw, "id", "claim"),
            contract_digest=_digest(raw, "contract_digest", "claim"),
            scope=_text(raw, "scope", "claim"),
            target=Target.from_dict(_mapping(raw.get("target"), "claim.target"),
                                    "claim.target"),
            expected_revision=_text(raw, "expected_revision", "claim"),
            claim_type=claim_type,
            extensions=dict(raw.get("extensions") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": self.id,
            "contract_digest": self.contract_digest,
            "scope": self.scope,
            "target": self.target.to_dict(),
            "expected_revision": self.expected_revision,
            "claim_type": self.claim_type,
        }
        if self.extensions:
            body["extensions"] = dict(self.extensions)
        return body


# ---------------------------------------------------------------------------
# EvidenceObservation
# ---------------------------------------------------------------------------

_OBSERVATION_REQUIRED = (
    "id", "run_id", "verification_round", "collector_id", "collector_version",
    "probe_id", "scope", "target", "binding_revision", "observed_revision",
    "source_group", "sequence", "observed_at", "elapsed_ms", "artifact_digest",
)


@dataclass(frozen=True)
class EvidenceObservation:
    id: str
    run_id: str
    verification_round: int
    collector_id: str
    collector_version: str
    probe_id: str
    scope: str
    target: Target
    binding_revision: str
    observed_revision: str | None
    source_group: str
    sequence: int
    observed_at: datetime
    elapsed_ms: int
    artifact_digest: str
    payload: dict[str, Any] | str | None = None
    error: dict[str, Any] | None = None
    extensions: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "EvidenceObservation":
        raw = _mapping(raw, "observation")
        _strict(raw, set(_OBSERVATION_REQUIRED) | {"payload", "error", "extensions"},
               "observation")
        missing = [key for key in _OBSERVATION_REQUIRED if key not in raw]
        if missing:
            # 缺字段（含 observed_revision 键缺失）按 MALFORMED，由求值器记录原因码。
            raise ContractError(f"observation 缺字段：{missing}")
        observed_revision = raw.get("observed_revision")
        if observed_revision is not None and (
            not isinstance(observed_revision, str) or not observed_revision
        ):
            raise ContractError("observation.observed_revision 必须是字符串或 null")
        payload = raw.get("payload")
        if payload is not None and not isinstance(payload, (dict, str)):
            raise ContractError("observation.payload 必须是对象、字符串或 null")
        error = raw.get("error")
        if error is not None:
            error = _mapping(error, "observation.error")
            code = error.get("code")
            if not isinstance(code, str) or not _ERROR_CODE_RE.fullmatch(code):
                raise ContractError("observation.error.code 不符合模式")
        if payload is None and error is None:
            raise ContractError("observation.payload 与 error 至少一个非 null")
        return cls(
            id=_ident(raw, "id", "observation"),
            run_id=_ident(raw, "run_id", "observation"),
            verification_round=_integer(raw, "verification_round", "observation", minimum=1),
            collector_id=_ident(raw, "collector_id", "observation"),
            collector_version=_text(raw, "collector_version", "observation"),
            probe_id=_ident(raw, "probe_id", "observation"),
            scope=_text(raw, "scope", "observation"),
            target=Target.from_dict(_mapping(raw.get("target"), "observation.target"),
                                    "observation.target"),
            binding_revision=_text(raw, "binding_revision", "observation"),
            observed_revision=observed_revision,
            source_group=_ident(raw, "source_group", "observation"),
            sequence=_integer(raw, "sequence", "observation", minimum=0),
            observed_at=parse_time(raw.get("observed_at")),
            elapsed_ms=_integer(raw, "elapsed_ms", "observation", minimum=0, maximum=1000),
            artifact_digest=_digest(raw, "artifact_digest", "observation"),
            payload=payload,
            error=dict(error) if error is not None else None,
            extensions=dict(raw.get("extensions") or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": self.id,
            "run_id": self.run_id,
            "verification_round": self.verification_round,
            "collector_id": self.collector_id,
            "collector_version": self.collector_version,
            "probe_id": self.probe_id,
            "scope": self.scope,
            "target": self.target.to_dict(),
            "binding_revision": self.binding_revision,
            "observed_revision": self.observed_revision,
            "source_group": self.source_group,
            "sequence": self.sequence,
            "observed_at": format_time(self.observed_at),
            "elapsed_ms": self.elapsed_ms,
            "artifact_digest": self.artifact_digest,
        }
        if self.payload is not None:
            body["payload"] = self.payload
        if self.error is not None:
            body["error"] = dict(self.error)
        if self.extensions:
            body["extensions"] = dict(self.extensions)
        return body


def payload_digest(payload: Any) -> str:
    """artifact_digest = canonical 摘要(payload)；只证明字节一致，不证明采集真实。"""
    return digest_of(payload)


# ---------------------------------------------------------------------------
# ObligationResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObligationResult:
    obligation_id: str
    value: str
    reason_codes: tuple[str, ...]
    used_evidence_ids: tuple[str, ...]
    rejected_evidence: tuple[dict[str, str], ...]
    checked_at: datetime
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.value not in EVIDENCE_VALUES:
            raise ContractError(f"obligation_result.value 非法：{self.value}")
        bad = [code for code in self.reason_codes if code not in REASON_CODES]
        if bad:
            raise ContractError(f"obligation_result 原因码非法：{bad}")
        if self.value == "TRUE" and self.reason_codes:
            raise ContractError("TRUE 的 obligation_result 不得带原因码")
        if self.value == "UNKNOWN" and not self.reason_codes:
            raise ContractError("UNKNOWN 的 obligation_result 必须至少一个原因码")

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "obligation_id": self.obligation_id,
            "value": self.value,
            "reason_codes": list(self.reason_codes),
            "used_evidence_ids": list(self.used_evidence_ids),
            "rejected_evidence": [dict(item) for item in self.rejected_evidence],
            "checked_at": format_time(self.checked_at),
        }
        if self.extensions:
            body["extensions"] = dict(self.extensions)
        return body

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ObligationResult":
        raw = _mapping(raw, "obligation_result")
        _strict(raw, {"obligation_id", "value", "reason_codes", "used_evidence_ids",
                      "rejected_evidence", "checked_at", "extensions"},
               "obligation_result")
        rejected = raw.get("rejected_evidence") or []
        return cls(
            obligation_id=_ident(raw, "obligation_id", "obligation_result"),
            value=_text(raw, "value", "obligation_result"),
            reason_codes=tuple(raw.get("reason_codes") or ()),
            used_evidence_ids=tuple(raw.get("used_evidence_ids") or ()),
            rejected_evidence=tuple(
                {"evidence_id": item.get("evidence_id"), "reason_code": item.get("reason_code")}
                for item in rejected
            ),
            checked_at=parse_time(raw.get("checked_at")),
            extensions=dict(raw.get("extensions") or {}),
        )


# ---------------------------------------------------------------------------
# VerificationReceipt
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VerificationReceipt:
    id: str
    contract_digest: str
    claim_digest: str
    evidence_snapshot_digest: str
    policy_version: str
    collector_versions: dict[str, str]
    run_id: str
    verification_round: int
    target: Target
    binding_revision: str
    observed_revision: str | None
    obligation_results: tuple[ObligationResult, ...]
    verdict: str
    receipt_state: str
    issued_at: datetime | None
    valid_until: datetime | None
    invalidation_event_ids: tuple[str, ...] = ()
    extensions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "id": self.id,
            "contract_digest": self.contract_digest,
            "claim_digest": self.claim_digest,
            "evidence_snapshot_digest": self.evidence_snapshot_digest,
            "policy_version": self.policy_version,
            "collector_versions": dict(self.collector_versions),
            "run_id": self.run_id,
            "verification_round": self.verification_round,
            "target": self.target.to_dict(),
            "binding_revision": self.binding_revision,
            "observed_revision": self.observed_revision,
            "obligation_results": [item.to_dict() for item in self.obligation_results],
            "verdict": self.verdict,
            "receipt_state": self.receipt_state,
            "issued_at": format_time(self.issued_at) if self.issued_at else None,
            "valid_until": format_time(self.valid_until) if self.valid_until else None,
            "invalidation_event_ids": list(self.invalidation_event_ids),
        }
        if self.extensions:
            body["extensions"] = dict(self.extensions)
        return body

    def snapshot_digest(self) -> str:
        return object_digest(self.to_dict())

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "VerificationReceipt":
        raw = _mapping(raw, "receipt")
        _strict(raw, {
            "id", "contract_digest", "claim_digest", "evidence_snapshot_digest",
            "policy_version", "collector_versions", "run_id", "verification_round",
            "target", "binding_revision", "observed_revision", "obligation_results",
            "verdict", "receipt_state", "issued_at", "valid_until",
            "invalidation_event_ids", "extensions",
        }, "receipt")
        issued_at = raw.get("issued_at")
        valid_until = raw.get("valid_until")
        return cls(
            id=_ident(raw, "id", "receipt"),
            contract_digest=_digest(raw, "contract_digest", "receipt"),
            claim_digest=_digest(raw, "claim_digest", "receipt"),
            evidence_snapshot_digest=_digest(raw, "evidence_snapshot_digest", "receipt"),
            policy_version=_text(raw, "policy_version", "receipt"),
            collector_versions=dict(raw.get("collector_versions") or {}),
            run_id=_ident(raw, "run_id", "receipt"),
            verification_round=_integer(raw, "verification_round", "receipt", minimum=1),
            target=Target.from_dict(_mapping(raw.get("target"), "receipt.target"),
                                    "receipt.target"),
            binding_revision=_text(raw, "binding_revision", "receipt"),
            observed_revision=raw.get("observed_revision"),
            obligation_results=tuple(
                ObligationResult.from_dict(item) for item in raw.get("obligation_results")
            ),
            verdict=_text(raw, "verdict", "receipt"),
            receipt_state=_text(raw, "receipt_state", "receipt"),
            issued_at=None if issued_at is None else parse_time(issued_at),
            valid_until=None if valid_until is None else parse_time(valid_until),
            invalidation_event_ids=tuple(raw.get("invalidation_event_ids") or ()),
            extensions=dict(raw.get("extensions") or {}),
        )
