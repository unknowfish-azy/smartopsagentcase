"""Dry-run quality gate for SmartOps JSON/JSONL training datasets."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from training.schema_registry import load_catalog, load_schema, schema_version


SCHEMAS = {
    "sft": ("instruction", "input", "output"),
    "preference": ("prompt", "chosen", "rejected", "reason"),
    "inspector": ("task", "agent_trace", "evidence", "policy", "expected"),
    "evidence": ("claim", "evidence", "label"),
}
VALID_LABELS = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED", "CONTRADICTED"}
UNSAFE_MARKERS = (
    "shell=true", "rm -rf /", "disable approval", "bypass permission",
    "ignore permission", "skip verification", "reveal chain of thought",
)
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
DIFFICULTY_LEVELS = {f"L{i}" for i in range(1, 11)}
EVIDENCE_STATUSES = {"DIRECT", "INDIRECT", "WEAK", "CONFLICTING", "INSUFFICIENT", "OUTDATED"}
DATA_CLASSES = {"REAL", "SYNTHETIC", "DEMO"}
V1_REQUIRED = tuple(load_schema("training_sample")["required"])
DATASET_TYPES = set(load_catalog()["dataset_types"])
SOURCE_TYPES = set(load_catalog()["source_types"])
TASK_OUTPUT_FIELDS = {
    "OPS_REASONING": (
        "diagnosis", "root_cause", "evidence", "confidence",
        "reasoning_summary", "plan", "next_tool", "risk",
        "approval_required", "verification_plan",
    ),
    "EVIDENCE_VERIFICATION": (
        "label", "reason", "supporting_evidence", "confidence",
    ),
    "TOOL_SELECTION": ("decision", "tool", "reason", "risk", "approval_required"),
    "RISK_DECISION": ("risk", "reason", "approval_required"),
    "RESULT_VERIFICATION": ("status", "reason", "replan_required"),
    "INSPECTION": (
        "decision", "category", "severity", "issues", "reason",
        "recommendation", "requires_human",
    ),
    "PREFERENCE_RANKING": ("chosen", "rejected", "reason", "principles"),
}


@dataclass
class QualityReport:
    dataset_type: str
    schema_version: str = "legacy"
    validation_mode: str = "auto"
    files: int = 0
    samples: int = 0
    valid: int = 0
    invalid: int = 0
    duplicates: int = 0
    unsafe: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _records(path: Path) -> Iterable[tuple[int, Any]]:
    if path.suffix.lower() == ".jsonl":
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                yield line_number, json.loads(line)
        return
    value = json.loads(path.read_text(encoding="utf-8"))
    for index, record in enumerate(value if isinstance(value, list) else [value], 1):
        yield index, record


def _dataset_files(directory: Path) -> list[Path]:
    """Exclude control-plane manifests from sample validation."""
    return sorted(
        path for path in (*directory.glob("*.json"), *directory.glob("*.jsonl"))
        if path.name != "manifest.json"
    )


def _empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _require(record: dict[str, Any], keys: Iterable[str]) -> list[str]:
    return [f"missing or empty field: {key}" for key in keys if key not in record or _empty(record[key])]


def _require_output(record: dict[str, Any], keys: Iterable[str]) -> list[str]:
    """Require output keys while allowing intentionally empty list fields."""
    allow_empty = {"evidence", "plan", "verification_plan", "issues", "principles"}
    return [
        f"missing or empty field: {key}"
        for key in keys
        if key not in record or (key not in allow_empty and _empty(record[key]))
    ]


def _number_in_range(value: Any, minimum: float, maximum: float) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and minimum <= value <= maximum


def _validate_v1(record: dict[str, Any], expected_type: str) -> list[str]:
    errors = _require(record, V1_REQUIRED)
    if errors:
        return errors

    if record.get("schema_version") != schema_version():
        errors.append("unsupported schema_version")
    actual_type = record.get("dataset_type")
    if actual_type not in DATASET_TYPES:
        errors.append("invalid dataset_type")
    if expected_type != "auto" and actual_type != expected_type.upper():
        errors.append(f"dataset_type mismatch: expected {expected_type.upper()}")

    environment = record.get("environment")
    if not isinstance(environment, dict):
        errors.append("environment must be an object")
    else:
        errors.extend(_require(environment, ("environment_id", "observed_at")))

    for index, item in enumerate(record.get("knowledge", [])):
        if not isinstance(item, dict):
            errors.append(f"knowledge[{index}] must be an object")
            continue
        errors.extend(f"knowledge[{index}]: {error}" for error in _require(
            item, ("knowledge_id", "source", "version", "service", "trust", "content")
        ))
        if not _number_in_range(item.get("trust"), 0, 1):
            errors.append(f"knowledge[{index}]: trust must be between 0 and 1")

    evidence_ids: set[str] = set()
    for index, item in enumerate(record.get("evidence", [])):
        if not isinstance(item, dict):
            errors.append(f"evidence[{index}] must be an object")
            continue
        errors.extend(f"evidence[{index}]: {error}" for error in _require(
            item, ("evidence_id", "source", "content", "timestamp", "relevance", "version")
        ))
        evidence_id = item.get("evidence_id")
        if evidence_id in evidence_ids:
            errors.append(f"evidence[{index}]: duplicate evidence_id")
        evidence_ids.add(evidence_id)
        if not _number_in_range(item.get("relevance"), 0, 1):
            errors.append(f"evidence[{index}]: relevance must be between 0 and 1")
        relation = item.get("support_relation")
        if relation is not None and relation not in VALID_LABELS | {"UNKNOWN"}:
            errors.append(f"evidence[{index}]: invalid support_relation")

    source = record.get("source")
    if not isinstance(source, dict):
        errors.append("source must be an object")
    else:
        errors.extend(f"source: {error}" for error in _require(
            source, ("source_type", "source_ref", "created_at", "data_class")
        ))
        if source.get("source_type") not in SOURCE_TYPES:
            errors.append("invalid source_type")
        if source.get("data_class") not in DATA_CLASSES:
            errors.append("invalid data_class")
        if source.get("source_type") == "SYNTHETIC_INCIDENT" and source.get("data_class") != "SYNTHETIC":
            errors.append("synthetic source must use SYNTHETIC data_class")
        if source.get("source_type") in {"REAL_LOG", "REAL_AGENT_TRACE"} and source.get("data_class") != "REAL":
            errors.append("real source must use REAL data_class")

    output = record.get("output")
    task_type = record.get("task_type")
    if not isinstance(output, dict):
        errors.append("output must be an object")
    elif task_type in TASK_OUTPUT_FIELDS:
        errors.extend(f"output: {error}" for error in _require_output(output, TASK_OUTPUT_FIELDS[task_type]))
        risk = output.get("risk")
        if "risk" in TASK_OUTPUT_FIELDS[task_type] and risk not in RISK_LEVELS:
            errors.append("output: invalid risk")
        if risk in {"HIGH", "CRITICAL"} and output.get("approval_required") is not True:
            errors.append("output: HIGH/CRITICAL risk requires approval")
        confidence = output.get("confidence")
        if confidence is not None and not _number_in_range(confidence, 0, 1):
            errors.append("output: confidence must be between 0 and 1")

    if record.get("dataset_type") == "PREFERENCE":
        preference = record.get("expected_behavior")
        if not isinstance(preference, dict):
            errors.append("expected_behavior must be an object")
        else:
            errors.extend(f"expected_behavior: {error}" for error in _require(
                preference, ("chosen", "rejected", "reason", "principles")
            ))
            if preference.get("chosen") == preference.get("rejected"):
                errors.append("chosen and rejected must differ")

    quality = record.get("quality")
    if not isinstance(quality, dict):
        errors.append("quality must be an object")
    else:
        errors.extend(f"quality: missing field: {key}" for key in ("status", "human_review", "checks") if key not in quality)

    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
    else:
        errors.extend(f"metadata: {error}" for error in _require(
            metadata, ("incident_family", "root_cause_group", "scenario_id")
        ))
    return errors


def _validate_governance_fields(record: dict[str, Any]) -> list[str]:
    """Strict Phase 7.4 metadata checks, opt-in to preserve the v1 API."""
    errors: list[str] = []
    for key in ("sample_id", "dataset_id", "dataset_version", "dataset_role", "source_reference", "created_at", "created_by"):
        if _empty(record.get(key)):
            errors.append(f"provenance: missing or empty field: {key}")
    if record.get("dataset_role") not in {"TRAINING", "VALIDATION", "TEST", "GOLDEN", "REGRESSION", "CANDIDATE_POOL"}:
        errors.append("provenance: invalid dataset_role")
    metadata = record.get("metadata", {})
    errors.extend(f"metadata: missing or empty field: {key}" for key in (
        "difficulty_level", "environment_family", "version_family"
    ) if _empty(metadata.get(key)))
    if metadata.get("difficulty_level") not in DIFFICULTY_LEVELS:
        errors.append("metadata: difficulty_level must be L1-L10")
    for index, item in enumerate(record.get("evidence", [])):
        if isinstance(item, dict):
            if _empty(item.get("evidence_status")):
                errors.append(f"evidence[{index}]: missing or empty field: evidence_status")
            elif item.get("evidence_status") not in EVIDENCE_STATUSES:
                errors.append(f"evidence[{index}]: invalid evidence_status")
    return errors


def validate_dataset(
    root: str | Path, dataset_type: str, *, validation_mode: str = "auto"
) -> QualityReport:
    if dataset_type not in SCHEMAS and dataset_type.lower() not in {
        item.lower() for item in DATASET_TYPES
    } and dataset_type != "auto":
        raise ValueError(f"unsupported dataset type: {dataset_type}")
    if validation_mode not in {"auto", "legacy", "v1", "governance"}:
        raise ValueError(f"unsupported validation mode: {validation_mode}")
    directory = Path(root)
    report = QualityReport(dataset_type=dataset_type, validation_mode=validation_mode)
    seen: set[str] = set()

    for path in _dataset_files(directory):
        report.files += 1
        try:
            records = list(_records(path))
        except (OSError, json.JSONDecodeError) as exc:
            report.invalid += 1
            report.errors.append({"file": str(path), "error": str(exc)})
            continue

        for line, record in records:
            report.samples += 1
            errors = []
            if not isinstance(record, dict):
                errors.append("sample must be an object")
            else:
                is_v1 = record.get("schema_version") is not None
                use_v1 = validation_mode in {"v1", "governance"} or (validation_mode == "auto" and is_v1)
                if use_v1:
                    report.schema_version = schema_version()
                    errors.extend(_validate_v1(record, dataset_type))
                    if validation_mode == "governance":
                        errors.extend(_validate_governance_fields(record))
                else:
                    if validation_mode == "v1":
                        errors.append("missing schema_version")
                    legacy_type = dataset_type.lower()
                    if legacy_type not in SCHEMAS:
                        errors.append("legacy validation requires sft/preference/inspector/evidence")
                    else:
                        errors.extend(_require(record, SCHEMAS[legacy_type]))
                        if legacy_type == "evidence" and record.get("label") not in VALID_LABELS:
                            errors.append("invalid evidence label")

            canonical = json.dumps(record, ensure_ascii=False, sort_keys=True)
            digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if digest in seen:
                report.duplicates += 1
                errors.append("duplicate sample")
            seen.add(digest)

            if any(marker in canonical.lower() for marker in UNSAFE_MARKERS):
                report.unsafe += 1
                errors.append("unsafe sample marker")

            if errors:
                report.invalid += 1
                report.errors.append({"file": str(path), "line": line, "errors": errors})
            else:
                report.valid += 1
    return report
