"""N08 独立 oracle：只依据 recovery-contract/v1 schema 与 semantics 判定。

边界（有意如此）：
- 只使用 Python 标准库；不 import ``agent.recovery_contracts`` 的任何模块，
  不读取 PREDICATE_REGISTRY，也不复用实现里的 canonical JSON/时间工具。
- 输入是普通 ``dict``/JSON 对象；输出与实现可比的逐义务三值、整体 verdict、
  原因码。实现侧的调用在实验脚本里单独完成，本模块不感知实现。
- 冻结阈值直接来自 ``docs/design/recovery-contract-v1/schema.json`` 与
  ``semantics.md``（见下方常量注释）。这是规范副本，不是实现副本。
- 不做真实探针调度；``decision_time``、观测顺序、授权 scope 全部由调用方显式
  传入，保证可重复。

已知解释边界（报告里会列为 UNKNOWN/局限）：
1. ``observed_revision is null`` 按 semantics §3.2 “未报告”映射为 UNDETERMINED。
2. 单来源组内同时出现 SUPPORT 与 COUNTER 时，按 §3.3 “来源/身份未确认的冲突”
   保守判 UNKNOWN/CONFLICT；两组以上独立来源出现 COUNTER 时判 FALSE。
3. 采样窗口按 §4.2 要求同组 A/B 观测 target_id 相同；契约 target 与义务 target
   不一致的用例会因此与实现产生差异（这是本 oracle 有意保留的独立性）。
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

# ---------------------------------------------------------------------------
# schema/semantics 冻结常量：优先从 schema.json 读取，读不到时回退到同值常量。
# ---------------------------------------------------------------------------

SCHEMA_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "design"
    / "recovery-contract-v1"
    / "schema.json"
)

SCHEMA_VERSION = "recovery-contract/v1"

_FALLBACK_WINDOW = {
    "sample_groups": 3,
    "min_first_last_gap_ms": 4000,
    "max_adjacent_gap_ms": 4000,
    "max_intra_group_skew_ms": 1250,
    "min_next_group_gap_ms": 2000,
}
_FALLBACK_BUDGETS = {
    "max_probe_calls": 12,
    "per_probe_timeout_ms": 1000,
    "run_deadline_ms": 30000,
    "evidence_ttl_ms": 15000,
}


def _read_schema_constants(definition: str, fallback: Mapping[str, int]) -> dict[str, int]:
    try:
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        properties = schema["$defs"][definition]["properties"]
    except (OSError, KeyError, TypeError, ValueError):
        return dict(fallback)
    result: dict[str, int] = {}
    for key, spec in properties.items():
        if isinstance(spec, Mapping) and "const" in spec:
            result[key] = spec["const"]
    if all(key in result for key in fallback):
        return result
    return dict(fallback)


WINDOW_CONSTANTS = _read_schema_constants("window", _FALLBACK_WINDOW)
BUDGET_CONSTANTS = _read_schema_constants("budgets", _FALLBACK_BUDGETS)
RECEIPT_TTL_MIN_MS = 1000

SUPPORT = "SUPPORT"
COUNTER = "COUNTER"
UNDETERMINED = "UNDETERMINED"

TRUE = "TRUE"
FALSE = "FALSE"
UNKNOWN = "UNKNOWN"

VERIFIED = "VERIFIED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT = "INSUFFICIENT"

KNOWN_PREDICATES = (
    "business_health_flag",
    "all_instances_recovered",
    "endpoint_reachable",
)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$")
_DIGEST_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
_ERROR_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")

_MISSING = object()

_CONTRACT_FIELDS = (
    "schema_version",
    "id",
    "version",
    "scope",
    "target",
    "expected_revision",
    "template_id",
    "template_version",
    "obligations",
    "source_groups",
    "window",
    "budgets",
    "expires_after",
    "digest",
)

_OBLIGATION_FIELDS = (
    "obligation_id",
    "predicate_id",
    "predicate_version",
    "required",
    "weight",
    "collector_ids",
    "source_groups",
    "binding_revision",
    "scope",
    "target",
)

_OBSERVATION_FIELDS = (
    "id",
    "run_id",
    "verification_round",
    "collector_id",
    "collector_version",
    "probe_id",
    "scope",
    "target",
    "binding_revision",
    "observed_revision",
    "source_group",
    "sequence",
    "observed_at",
    "elapsed_ms",
    "artifact_digest",
)

_TARGET_KINDS = ("SERVICE", "PROCESS", "ENDPOINT")


# ---------------------------------------------------------------------------
# 独立 canonical JSON / digest / 时间工具（按 semantics §2.1）
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
    """删除对象自身 digest 字段后的 canonical 摘要（semantics §2.1）。"""
    return digest_of({key: value for key, value in mapping.items() if key != "digest"})


def parse_time(value: Any) -> datetime:
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value:
        try:
            moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"非法 date-time：{value!r}") from exc
    else:
        raise ValueError(f"需要 date-time，得到 {value!r}")
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_time(value: Any) -> str:
    return parse_time(value).isoformat().replace("+00:00", "Z")


def _ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


# ---------------------------------------------------------------------------
# 结果结构
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ObligationVerdict:
    obligation_id: str
    value: str
    reason_codes: tuple[str, ...]
    used_evidence_ids: tuple[str, ...]
    rejected_evidence: tuple[dict[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "obligation_id": self.obligation_id,
            "value": self.value,
            "reason_codes": list(self.reason_codes),
            "used_evidence_ids": list(self.used_evidence_ids),
            "rejected_evidence": [dict(item) for item in self.rejected_evidence],
        }


@dataclass(frozen=True)
class WindowVerdict:
    valid_groups: int = 0
    total_groups: int = 0
    satisfied: bool = False
    reasons: tuple[str, ...] = ()
    group_times: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid_groups": self.valid_groups,
            "total_groups": self.total_groups,
            "satisfied": self.satisfied,
            "reasons": list(self.reasons),
            "group_times": list(self.group_times),
        }


@dataclass
class OracleDecision:
    verdict: str
    obligation_results: list[ObligationVerdict] = field(default_factory=list)
    window: WindowVerdict = field(default_factory=WindowVerdict)
    reason_codes: tuple[str, ...] = ()
    rejected: list[dict[str, str]] = field(default_factory=list)
    contract_rejected: bool = False
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "reason_codes": list(self.reason_codes),
            "obligation_results": [item.to_dict() for item in self.obligation_results],
            "window": self.window.to_dict(),
            "rejected": [dict(item) for item in self.rejected],
            "contract_rejected": self.contract_rejected,
            "notes": list(self.notes),
        }


# ---------------------------------------------------------------------------
# 基础校验
# ---------------------------------------------------------------------------

def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return _is_int(value) or isinstance(value, float)


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _is_digest(value: Any) -> bool:
    return isinstance(value, str) and bool(_DIGEST_RE.fullmatch(value))


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


def _payload_object(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, Mapping):
        return dict(payload)
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError):
            return None
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return None


def _lookup(body: Mapping[str, Any], path: str) -> Any:
    current: Any = body
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _validate_target(raw: Any, where: str, notes: list[str]) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        notes.append(f"{where} 必须是对象")
        return None
    target_id = raw.get("target_id")
    target_kind = raw.get("target_kind")
    if not _is_id(target_id):
        notes.append(f"{where}.target_id 不合法")
        return None
    if target_kind not in _TARGET_KINDS:
        notes.append(f"{where}.target_kind 不合法")
        return None
    endpoint = raw.get("endpoint")
    if endpoint is not None and not isinstance(endpoint, str):
        notes.append(f"{where}.endpoint 类型不合法")
        return None
    return {"target_id": target_id, "target_kind": target_kind, "endpoint": endpoint}


def _validate_contract(raw: Any) -> tuple[dict[str, Any] | None, str | None]:
    notes: list[str] = []
    if not isinstance(raw, Mapping):
        return None, "contract 必须是对象"
    missing = [key for key in _CONTRACT_FIELDS if key not in raw]
    if missing:
        return None, f"contract 缺字段：{missing}"
    if raw.get("schema_version") != SCHEMA_VERSION:
        return None, f"contract.schema_version 必须是 {SCHEMA_VERSION}"
    if not _is_id(raw.get("id")):
        return None, "contract.id 不合法"
    if not _is_text(raw.get("version")):
        return None, "contract.version 不合法"
    if not _is_text(raw.get("scope")):
        return None, "contract.scope 不合法"
    if not _is_text(raw.get("expected_revision")):
        return None, "contract.expected_revision 不合法"
    if not _is_text(raw.get("template_id")) or not _is_text(raw.get("template_version")):
        return None, "contract.template_id/template_version 不合法"
    target = _validate_target(raw.get("target"), "contract.target", notes)
    if target is None:
        return None, notes[-1]

    obligations_raw = raw.get("obligations")
    if not isinstance(obligations_raw, list) or not obligations_raw:
        # semantics §2：空义务集必须被拒绝。
        return None, "contract.obligations 至少 1 项"

    obligations: list[dict[str, Any]] = []
    for index, item in enumerate(obligations_raw):
        where = f"contract.obligations[{index}]"
        if not isinstance(item, Mapping):
            return None, f"{where} 必须是对象"
        missing = [key for key in _OBLIGATION_FIELDS if key not in item]
        if missing:
            return None, f"{where} 缺字段：{missing}"
        if not _is_id(item.get("obligation_id")):
            return None, f"{where}.obligation_id 不合法"
        predicate_id = item.get("predicate_id")
        if not isinstance(predicate_id, str) or predicate_id not in KNOWN_PREDICATES:
            # V1 只允许已审核模板；未知谓词不能自行解释。
            return None, f"{where}.predicate_id 未登记：{predicate_id!r}"
        if not _is_text(item.get("predicate_version")):
            return None, f"{where}.predicate_version 不合法"
        if not isinstance(item.get("required"), bool):
            return None, f"{where}.required 必须是 bool"
        if not _is_number(item.get("weight")):
            return None, f"{where}.weight 必须是数字"
        collector_ids = item.get("collector_ids")
        if not isinstance(collector_ids, list) or not collector_ids:
            return None, f"{where}.collector_ids 至少 1 项"
        if not all(_is_id(value) for value in collector_ids):
            return None, f"{where}.collector_ids 含非法 ID"
        source_groups = item.get("source_groups")
        if not isinstance(source_groups, list) or not source_groups:
            return None, f"{where}.source_groups 至少 1 项"
        if not all(_is_id(value) for value in source_groups):
            return None, f"{where}.source_groups 含非法 ID"
        if not _is_text(item.get("binding_revision")):
            return None, f"{where}.binding_revision 不合法"
        if not _is_text(item.get("scope")):
            return None, f"{where}.scope 不合法"
        obligation_target = _validate_target(item.get("target"), f"{where}.target", notes)
        if obligation_target is None:
            return None, notes[-1]
        params = item.get("predicate_params", {})
        if params is None:
            params = {}
        if not isinstance(params, Mapping):
            return None, f"{where}.predicate_params 必须是对象"
        obligations.append(
            {
                "obligation_id": item["obligation_id"],
                "predicate_id": predicate_id,
                "predicate_version": item["predicate_version"],
                "required": item["required"],
                "weight": item["weight"],
                "collector_ids": tuple(collector_ids),
                "source_groups": tuple(source_groups),
                "binding_revision": item["binding_revision"],
                "scope": item["scope"],
                "target": obligation_target,
                "predicate_params": dict(params),
            }
        )

    source_groups_raw = raw.get("source_groups")
    if not isinstance(source_groups_raw, list) or len(source_groups_raw) < 2:
        return None, "contract.source_groups 至少 2 项"
    if not all(_is_id(value) for value in source_groups_raw):
        return None, "contract.source_groups 含非法 ID"

    window_raw = raw.get("window")
    if not isinstance(window_raw, Mapping):
        return None, "contract.window 必须是对象"
    for key, expected in WINDOW_CONSTANTS.items():
        if not _is_int(window_raw.get(key)) or window_raw.get(key) != expected:
            return None, f"contract.window.{key} 冻结为 {expected}"

    budgets_raw = raw.get("budgets")
    if not isinstance(budgets_raw, Mapping):
        return None, "contract.budgets 必须是对象"
    for key, expected in BUDGET_CONSTANTS.items():
        if not _is_int(budgets_raw.get(key)) or budgets_raw.get(key) != expected:
            return None, f"contract.budgets.{key} 冻结为 {expected}"
    receipt_ttl = budgets_raw.get("receipt_ttl_ms")
    if not _is_int(receipt_ttl) or receipt_ttl < RECEIPT_TTL_MIN_MS:
        return None, "contract.budgets.receipt_ttl_ms 至少 1000"

    expires_after = raw.get("expires_after")
    if not _is_int(expires_after) or expires_after < 1000:
        return None, "contract.expires_after 至少 1000"

    digest = raw.get("digest")
    if not _is_digest(digest):
        return None, "contract.digest 格式不合法"
    if digest != object_digest(raw):
        # semantics §2.1：冻结历史被改动即拒绝，不边拒绝篡改边继续求值。
        return None, "contract.digest 与 canonical 摘要不一致"

    return (
        {
            "scope": raw["scope"],
            "target": target,
            "expected_revision": raw["expected_revision"],
            "obligations": obligations,
            "source_groups": tuple(source_groups_raw),
            "window": dict(WINDOW_CONSTANTS),
            "budgets": dict(budgets_raw),
        },
        None,
    )


# ---------------------------------------------------------------------------
# 观测解析与资格（semantics §3.1）
# ---------------------------------------------------------------------------

def _parse_observation(
    raw: Any,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """返回 (解析后的观测, 解析失败原因码, 可用于审计的 evidence_id)。"""
    if not isinstance(raw, Mapping):
        return None, "MALFORMED", None
    evidence_id = raw.get("id") if isinstance(raw.get("id"), str) and raw.get("id") else None
    missing = [key for key in _OBSERVATION_FIELDS if key not in raw]
    if missing:
        return None, "MALFORMED", evidence_id
    if not _is_id(raw.get("id")):
        return None, "MALFORMED", evidence_id
    if not _is_id(raw.get("run_id")):
        return None, "MALFORMED", evidence_id
    if not _is_int(raw.get("verification_round")) or raw["verification_round"] < 1:
        return None, "MALFORMED", evidence_id
    if not _is_id(raw.get("collector_id")):
        return None, "MALFORMED", evidence_id
    if not _is_text(raw.get("collector_version")):
        return None, "MALFORMED", evidence_id
    if not _is_id(raw.get("probe_id")):
        return None, "MALFORMED", evidence_id
    if not _is_text(raw.get("scope")):
        return None, "MALFORMED", evidence_id
    target = _validate_target(raw.get("target"), "observation.target", [])
    if target is None:
        return None, "MALFORMED", evidence_id
    if not _is_text(raw.get("binding_revision")):
        return None, "MALFORMED", evidence_id
    observed_revision = raw.get("observed_revision")
    if observed_revision is not None and not _is_text(observed_revision):
        return None, "MALFORMED", evidence_id
    if not _is_id(raw.get("source_group")):
        return None, "MALFORMED", evidence_id
    if not _is_int(raw.get("sequence")) or raw["sequence"] < 0:
        return None, "MALFORMED", evidence_id
    try:
        observed_at = parse_time(raw.get("observed_at"))
    except ValueError:
        return None, "MALFORMED", evidence_id
    if not _is_int(raw.get("elapsed_ms")) or not 0 <= raw["elapsed_ms"] <= 1000:
        return None, "MALFORMED", evidence_id
    if not _is_digest(raw.get("artifact_digest")):
        return None, "MALFORMED", evidence_id

    payload = raw.get("payload")
    if payload is not None and not isinstance(payload, (Mapping, str)):
        return None, "MALFORMED", evidence_id
    error = raw.get("error")
    if error is not None:
        if not isinstance(error, Mapping):
            return None, "MALFORMED", evidence_id
        code = error.get("code")
        if not isinstance(code, str) or not _ERROR_CODE_RE.fullmatch(code):
            return None, "MALFORMED", evidence_id
        error = dict(error)
    if payload is None and error is None:
        return None, "MALFORMED", evidence_id
    if isinstance(payload, Mapping):
        payload = dict(payload)

    expected_digest = digest_of(payload if payload is not None else error)
    artifact_ok = raw["artifact_digest"] == expected_digest

    return (
        {
            "id": raw["id"],
            "run_id": raw["run_id"],
            "verification_round": raw["verification_round"],
            "collector_id": raw["collector_id"],
            "collector_version": raw["collector_version"],
            "probe_id": raw["probe_id"],
            "scope": raw["scope"],
            "target": target,
            "binding_revision": raw["binding_revision"],
            "observed_revision": observed_revision,
            "source_group": raw["source_group"],
            "sequence": raw["sequence"],
            "observed_at": observed_at,
            "observed_at_ms": _ms(observed_at),
            "elapsed_ms": raw["elapsed_ms"],
            "artifact_digest": raw["artifact_digest"],
            "artifact_ok": artifact_ok,
            "payload": payload,
            "error": error,
        },
        None,
        raw["id"],
    )


def _common_rejection(
    observation: Mapping[str, Any],
    decision_time: datetime,
) -> str | None:
    if observation["observed_at_ms"] > _ms(decision_time):
        return "MALFORMED"
    if not observation["artifact_ok"]:
        return "MALFORMED"
    return None


def _rejection(
    observation: Mapping[str, Any],
    contract: Mapping[str, Any],
    obligation: Mapping[str, Any],
    decision_time: datetime,
    run_id: str | None,
    verification_round: int | None,
    authorized_scopes: frozenset[str],
) -> str | None:
    """按 §3.1 的 ∧ 链返回首个原因码；顺序与实现文档一致。"""
    common = _common_rejection(observation, decision_time)
    if common is not None:
        return common
    if verification_round is not None and observation["verification_round"] != verification_round:
        return "MISSING"
    if run_id is not None and observation["run_id"] != run_id:
        return "STALE"
    if observation["scope"] not in authorized_scopes:
        return "MISSING"
    if observation["target"]["target_id"] != obligation["target"]["target_id"]:
        return "WRONG_TARGET"
    if observation["collector_id"] not in obligation["collector_ids"]:
        return "MALFORMED"
    if observation["source_group"] not in obligation["source_groups"]:
        return "MALFORMED"
    if observation["binding_revision"] != contract["expected_revision"]:
        return "WRONG_REVISION"
    if _ms(decision_time) - observation["observed_at_ms"] > contract["budgets"]["evidence_ttl_ms"]:
        return "STALE"
    return None


# ---------------------------------------------------------------------------
# 谓词（semantics §8.1；独立实现，不引用实现注册表）
# ---------------------------------------------------------------------------

def _predicate_value(
    observation: Mapping[str, Any],
    obligation: Mapping[str, Any],
    expected_revision: str,
) -> tuple[str, str | None]:
    if observation["error"] is not None:
        code = observation["error"].get("code")
        if code == "TIMEOUT":
            if (
                obligation["predicate_id"] == "endpoint_reachable"
                and obligation["predicate_params"].get("timeout_is_failure") is True
            ):
                return COUNTER, None
            return UNDETERMINED, "TIMEOUT"
        return UNDETERMINED, "MALFORMED"

    # semantics §3.2：observed_revision 为 null 表示响应未报告，不能当 SUPPORT。
    if observation["observed_revision"] is None:
        return UNDETERMINED, "MISSING"
    if observation["observed_revision"] != expected_revision:
        return COUNTER, "WRONG_REVISION"

    predicate_id = obligation["predicate_id"]
    params = obligation["predicate_params"]
    payload = observation["payload"]

    if predicate_id == "business_health_flag":
        body = _payload_object(payload)
        if body is None:
            return UNDETERMINED, "MALFORMED"
        path = params.get("field")
        if not _is_text(path):
            return UNDETERMINED, "MALFORMED"
        actual = _strict_bool(_lookup(body, path))
        if actual is None:
            return UNDETERMINED, "MALFORMED"
        expected = params.get("expected", True)
        if not isinstance(expected, bool):
            return UNDETERMINED, "MALFORMED"
        return (SUPPORT, None) if actual is expected else (COUNTER, None)

    if predicate_id == "all_instances_recovered":
        body = _payload_object(payload)
        if body is None:
            return UNDETERMINED, "MALFORMED"
        path = params.get("field", "instances")
        if not _is_text(path):
            return UNDETERMINED, "MALFORMED"
        instances = _lookup(body, path)
        if not isinstance(instances, list) or not instances:
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

    if predicate_id == "endpoint_reachable":
        # semantics §8.1：携带状态码时只有 2xx/3xx 可作 SUPPORT。
        body = _payload_object(payload)
        if body is not None:
            status = body.get("status_code", body.get("http_status"))
            if status is not None:
                try:
                    status_int = int(status)
                except (TypeError, ValueError):
                    return UNDETERMINED, "MALFORMED"
                if not 200 <= status_int <= 399:
                    return UNDETERMINED, "MALFORMED"
        return SUPPORT, None

    return UNDETERMINED, "MALFORMED"


def _observation_value(
    observation: Mapping[str, Any],
    obligation: Mapping[str, Any],
    expected_revision: str,
) -> tuple[str, str | None]:
    return _predicate_value(observation, obligation, expected_revision)


# ---------------------------------------------------------------------------
# 采样窗口（semantics §4.2）
# ---------------------------------------------------------------------------

def _ordered(observations: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return sorted(
        observations,
        key=lambda item: (item["observed_at_ms"], item["sequence"], item["id"]),
    )


def _by_source_group(
    observations: Sequence[Mapping[str, Any]],
) -> dict[str, list[Mapping[str, Any]]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for observation in observations:
        grouped.setdefault(observation["source_group"], []).append(observation)
    return {key: _ordered(value) for key, value in grouped.items()}


def _evaluate_window(
    contract: Mapping[str, Any],
    parsed: Sequence[Mapping[str, Any]],
    rejections_by_obligation: Mapping[str, Mapping[str, str]],
) -> WindowVerdict:
    eligible = [
        observation
        for observation in parsed
        if any(observation["id"] not in mapping for mapping in rejections_by_obligation.values())
    ]
    # §4.2：同一组 A/B 必须同 target；契约 target 是组级目标基准。
    contract_target = contract["target"]["target_id"]
    eligible = [
        observation for observation in eligible
        if observation["target"]["target_id"] == contract_target
    ]
    grouped = _by_source_group(eligible)
    if not all(group in grouped for group in contract["source_groups"]):
        return WindowVerdict(total_groups=0, satisfied=False, reasons=("MISSING",))

    total = min(len(grouped[group]) for group in contract["source_groups"])
    valid: list[tuple[datetime, list[Mapping[str, Any]]]] = []
    for index in range(total):
        members = [grouped[group][index] for group in contract["source_groups"]]
        times = [item["observed_at_ms"] for item in members]
        skew = max(times) - min(times)
        if skew > contract["window"]["max_intra_group_skew_ms"]:
            continue
        latest = max(members, key=lambda item: item["observed_at_ms"])
        valid.append((latest["observed_at"], members))

    reasons: list[str] = []
    if len(valid) < contract["window"]["sample_groups"]:
        reasons.append("MISSING")

    gaps_ok = True
    for previous, current in zip(valid, valid[1:]):
        previous_time, _ = previous
        current_time, members = current
        gap = _ms(current_time) - _ms(previous_time)
        if gap > contract["window"]["max_adjacent_gap_ms"]:
            gaps_ok = False
        earliest_start = min(
            item["observed_at_ms"] - item["elapsed_ms"] for item in members
        )
        if earliest_start < _ms(previous_time) + contract["window"]["min_next_group_gap_ms"]:
            gaps_ok = False

    if valid:
        span = _ms(valid[-1][0]) - _ms(valid[0][0])
        if span < contract["window"]["min_first_last_gap_ms"]:
            gaps_ok = False

    if not gaps_ok:
        reasons.append("MISSING")

    reasons = list(dict.fromkeys(reasons))
    satisfied = (
        len(valid) >= contract["window"]["sample_groups"]
        and gaps_ok
        and not reasons
    )
    return WindowVerdict(
        valid_groups=len(valid),
        total_groups=total,
        satisfied=satisfied,
        reasons=tuple(reasons),
        group_times=tuple(format_time(moment) for moment, _ in valid),
    )


# ---------------------------------------------------------------------------
# 义务求值（semantics §3.2/§3.3）
# ---------------------------------------------------------------------------

def _obligation_verdict(
    contract: Mapping[str, Any],
    obligation: Mapping[str, Any],
    parsed: Sequence[Mapping[str, Any]],
    rejections: Mapping[str, str],
    decision_time: datetime,
    parse_failure_codes: Sequence[str],
) -> tuple[ObligationVerdict, set[str]]:
    relevant = [
        observation for observation in parsed
        if observation["source_group"] in obligation["source_groups"]
    ]
    grouped = _by_source_group(relevant)
    sample_slots = contract["window"]["sample_groups"]

    counters: list[Mapping[str, Any]] = []
    counter_codes: list[str] = []
    slot_evidence: set[str] = set()
    unfilled_slots = 0
    eligible_support = False
    ineligible_counter = False

    for observation in relevant:
        reason = rejections.get(observation["id"])
        if reason is None:
            value, code = _observation_value(observation, obligation, contract["expected_revision"])
            if value == COUNTER:
                counters.append(observation)
                if code:
                    counter_codes.append(code)
            elif value == SUPPORT:
                eligible_support = True
        else:
            raw_value, _ = _observation_value(
                observation, obligation, contract["expected_revision"]
            )
            if raw_value == COUNTER:
                ineligible_counter = True

    for index in range(sample_slots):
        for source_group in obligation["source_groups"]:
            members = grouped.get(source_group, [])
            observation = members[index] if index < len(members) else None
            if observation is None:
                unfilled_slots += 1
                continue
            if rejections.get(observation["id"]) is not None:
                unfilled_slots += 1
                continue
            value, _ = _observation_value(observation, obligation, contract["expected_revision"])
            if value != SUPPORT:
                unfilled_slots += 1
                continue
            slot_evidence.add(observation["id"])

    rejected = tuple(
        {"evidence_id": observation["id"], "reason_code": rejections[observation["id"]]}
        for observation in relevant
        if observation["id"] in rejections
    )

    if counters:
        # §3.3：来源/身份未确认的单来源冲突只构成 UNKNOWN；已确认的独立来源反例
        # 必须直接 FALSE，不得多数投票。这里用“义务只要求一个来源组”作为
        # “无独立来源可确认反例”的 schema 内可判定代理。
        single_group_conflict = (
            len(set(obligation["source_groups"])) == 1
            and eligible_support
            and any(item["source_group"] in obligation["source_groups"] for item in counters)
        )
        if single_group_conflict:
            return (
                ObligationVerdict(
                    obligation_id=obligation["obligation_id"],
                    value=UNKNOWN,
                    reason_codes=("CONFLICT",),
                    used_evidence_ids=(),
                    rejected_evidence=rejected,
                ),
                slot_evidence,
            )
        used = tuple(sorted({item["id"] for item in counters}))
        return (
            ObligationVerdict(
                obligation_id=obligation["obligation_id"],
                value=FALSE,
                reason_codes=tuple(dict.fromkeys(counter_codes)),
                used_evidence_ids=used,
                rejected_evidence=rejected,
            ),
            slot_evidence,
        )

    if unfilled_slots == 0 and slot_evidence:
        return (
            ObligationVerdict(
                obligation_id=obligation["obligation_id"],
                value=TRUE,
                reason_codes=(),
                used_evidence_ids=tuple(sorted(slot_evidence)),
                rejected_evidence=rejected,
            ),
            slot_evidence,
        )

    codes: list[str] = []
    codes.extend(parse_failure_codes)
    for observation in relevant:
        reason = rejections.get(observation["id"])
        if reason is not None:
            codes.append(reason)
        else:
            value, code = _observation_value(observation, obligation, contract["expected_revision"])
            if value == UNDETERMINED and code:
                codes.append(code)
    if eligible_support and ineligible_counter:
        codes.append("CONFLICT")
    if unfilled_slots:
        codes.append("MISSING")
    if not codes:
        codes.append("MISSING")

    return (
        ObligationVerdict(
            obligation_id=obligation["obligation_id"],
            value=UNKNOWN,
            reason_codes=tuple(dict.fromkeys(codes)),
            used_evidence_ids=(),
            rejected_evidence=rejected,
        ),
        slot_evidence,
    )


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def judge(
    contract: Any,
    observations: Iterable[Any],
    decision_time: Any,
    *,
    run_id: str | None = None,
    verification_round: int | None = None,
    authorized_scopes: Iterable[str] | None = None,
    claim: Any = None,
) -> OracleDecision:
    """独立判定入口；输入/输出均为普通 Python 对象。"""
    validated, contract_error = _validate_contract(contract)
    if validated is None:
        return OracleDecision(
            verdict=INSUFFICIENT,
            reason_codes=("MISSING",),
            contract_rejected=True,
            notes=(contract_error or "contract 不合格",),
        )

    if claim is not None:
        if not isinstance(claim, Mapping):
            return OracleDecision(
                verdict=INSUFFICIENT,
                reason_codes=("MISSING",),
                contract_rejected=True,
                notes=("claim 必须是对象",),
            )
        if claim.get("claim_type") != "BUSINESS_RECOVERY":
            return OracleDecision(
                verdict=INSUFFICIENT,
                reason_codes=("MISSING",),
                contract_rejected=True,
                notes=("claim.claim_type 必须是 BUSINESS_RECOVERY",),
            )
        if claim.get("contract_digest") != contract.get("digest"):
            return OracleDecision(
                verdict=INSUFFICIENT,
                reason_codes=("MISSING",),
                contract_rejected=True,
                notes=("claim.contract_digest 与 contract.digest 不一致",),
            )

    parsed: list[dict[str, Any]] = []
    parse_failure_codes: list[str] = []
    rejected: list[dict[str, str]] = []
    seen: set[str] = set()

    for raw in observations:
        observation, code, evidence_id = _parse_observation(raw)
        if observation is None:
            parse_failure_codes.append(code or "MALFORMED")
            if evidence_id:
                rejected.append({"evidence_id": evidence_id, "reason_code": code or "MALFORMED"})
            continue
        if observation["id"] in seen:
            # 重复 ID 不算新增采样；保留审计但不填槽。
            rejected.append({"evidence_id": observation["id"], "reason_code": "MISSING"})
            continue
        seen.add(observation["id"])
        parsed.append(observation)

    try:
        decision = parse_time(decision_time)
    except ValueError:
        return OracleDecision(
            verdict=INSUFFICIENT,
            reason_codes=("MALFORMED",),
            contract_rejected=True,
            notes=(f"decision_time 非法：{decision_time!r}",),
        )

    scopes = (
        frozenset(authorized_scopes)
        if authorized_scopes is not None
        else frozenset({validated["scope"]})
    )

    # 资格是逐义务判定的；窗口取“至少对一个义务合格”的并集。
    rejections_by_obligation: dict[str, dict[str, str]] = {}
    for obligation in validated["obligations"]:
        mapping: dict[str, str] = {}
        for observation in parsed:
            reason = _rejection(
                observation,
                validated,
                obligation,
                decision,
                run_id,
                verification_round,
                scopes,
            )
            if reason is not None:
                mapping[observation["id"]] = reason
        rejections_by_obligation[obligation["obligation_id"]] = mapping

    results: list[ObligationVerdict] = []
    used_slot_ids: set[str] = set()
    for obligation in validated["obligations"]:
        result, slots = _obligation_verdict(
            validated,
            obligation,
            parsed,
            rejections_by_obligation[obligation["obligation_id"]],
            decision,
            parse_failure_codes,
        )
        results.append(result)
        if obligation["required"] and result.value == TRUE:
            used_slot_ids.update(slots)

    window = _evaluate_window(validated, parsed, rejections_by_obligation)

    required_values = [
        result.value
        for obligation, result in zip(validated["obligations"], results)
        if obligation["required"]
    ]
    if any(value == FALSE for value in required_values):
        verdict = CONTRADICTED
    elif all(value == TRUE for value in required_values) and window.satisfied:
        verdict = VERIFIED
    else:
        verdict = INSUFFICIENT

    overall_codes: list[str] = []
    for result in results:
        for code in result.reason_codes:
            if code not in overall_codes:
                overall_codes.append(code)

    dedup_rejected: list[dict[str, str]] = []
    seen_rejections: set[tuple[str, str]] = set()
    for item in rejected:
        key = (item["evidence_id"], item["reason_code"])
        if key not in seen_rejections:
            seen_rejections.add(key)
            dedup_rejected.append(item)
    for mapping in rejections_by_obligation.values():
        for evidence_id, code in mapping.items():
            key = (evidence_id, code)
            if key in seen_rejections:
                continue
            seen_rejections.add(key)
            dedup_rejected.append({"evidence_id": evidence_id, "reason_code": code})

    return OracleDecision(
        verdict=verdict,
        obligation_results=results,
        window=window,
        reason_codes=tuple(overall_codes),
        rejected=dedup_rejected,
    )
