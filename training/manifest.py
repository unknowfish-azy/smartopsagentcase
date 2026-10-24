"""Create truthful dataset manifests from validated JSON/JSONL directories."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.dataset_validator import validate_dataset


DATASET_TYPES = {
    "sft": "SFT",
    "preference": "PREFERENCE",
    "inspector": "INSPECTOR",
    "evidence": "EVIDENCE",
    "tool_call": "TOOL_SELECTION",
    "safety": "SAFETY",
    "verification": "VERIFICATION",
}
VALIDATOR_TYPES = {
    "sft": "sft",
    "preference": "preference",
    "inspector": "inspector",
    "evidence": "evidence",
    "tool_call": "TOOL_SELECTION",
    "safety": "SAFETY",
    "verification": "VERIFICATION",
}


def _file_hashes(directory: Path) -> list[bytes]:
    return [path.read_bytes() for path in sorted((*directory.glob("*.json"), *directory.glob("*.jsonl"))) if path.name != "manifest.json"]


def build_manifest(directory: str | Path, dataset_key: str, *, version: str = "v0.1") -> dict[str, Any]:
    """Build a manifest; empty directories remain DRAFT and are not READY."""
    if dataset_key not in DATASET_TYPES:
        raise ValueError(f"unsupported dataset key: {dataset_key}")
    root = Path(directory)
    report = validate_dataset(root, VALIDATOR_TYPES[dataset_key], validation_mode="auto")
    files = _file_hashes(root)
    digest = hashlib.sha256(b"".join(files)).hexdigest() if files else None
    source_types: set[str] = set()
    approved_count = 0
    for path in sorted((*root.glob("*.json"), *root.glob("*.jsonl"))):
        if path.name == "manifest.json":
            continue
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, dict) and isinstance(item.get("source"), dict):
                    source_types.add(str(item["source"].get("source_type", "UNKNOWN")))
                if isinstance(item, dict):
                    quality = item.get("quality")
                    if isinstance(quality, dict) and quality.get("human_review") == "APPROVED":
                        approved_count += 1
        except (OSError, json.JSONDecodeError):
            source_types.add("UNKNOWN")
    # A valid sample is not automatically trainable. Promotion requires explicit human approval.
    status = "READY" if approved_count > 0 and report.invalid == 0 and report.unsafe == 0 else "DRAFT"
    dataset_id = f"smartops-{dataset_key.replace('_', '-')}"
    content_hash = digest
    role = "CANDIDATE_POOL" if dataset_key == "sft" and approved_count == 0 else "TRAINING"
    manifest = {
        "dataset_id": dataset_id,
        "version": version,
        "dataset_version": version,
        "dataset_role": role,
        "schema_version": "1.0.0",
        "dataset_type": DATASET_TYPES[dataset_key],
        "source_types": sorted(source_types),
        "source_description": "Generated from governed SmartOps dataset records; approval is human-controlled.",
        "created_by": "smartops-manifest-builder",
        "sample_count": report.samples,
        "approved_count": approved_count,
        "train_count": 0,
        "validation_count": 0,
        "test_count": 0,
        "splits": {"train": 0, "validation": 0, "test": 0, "strategy": "NOT_SPLIT"},
        "duplicate_count": report.duplicates,
        "invalid_count": report.invalid,
        "unsafe_count": report.unsafe,
        "leakage_count": 0,
        "hash": digest,
        "content_hash": content_hash,
        "manifest_hash": None,
        "evaluation_only": False,
        "frozen": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "quality_report": "../quality_report.json",
        "leakage_report": None,
    }
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode("utf-8")
    manifest["manifest_hash"] = hashlib.sha256(canonical).hexdigest()
    return manifest


def write_manifests(root: str | Path) -> dict[str, dict[str, Any]]:
    base = Path(root)
    results: dict[str, dict[str, Any]] = {}
    for key in DATASET_TYPES:
        manifest = build_manifest(base / key, key)
        (base / key / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        results[key] = manifest
    return results


__all__ = ["DATASET_TYPES", "build_manifest", "write_manifests"]
