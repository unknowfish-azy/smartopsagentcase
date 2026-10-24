"""Phase 7.4 dataset-role and provenance reporting.

This is read-only with respect to samples: it reports governance gaps without
promoting candidates or turning derived cases into independent Golden data.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from training.dataset_validator import validate_dataset


def _load_records(folder: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(value, dict):
                records.append(value)
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    return records


def build_report(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    candidates = _load_records(base / "data" / "training" / "candidates")
    golden_path = base / "data" / "evaluation" / "prompt-baseline" / "golden-cases.json"
    golden = json.loads(golden_path.read_text(encoding="utf-8")) if golden_path.exists() else []
    source = Counter(str(item.get("source", {}).get("data_class", "UNKNOWN")) for item in candidates)
    states = Counter(str(item.get("state", "CANDIDATE")) for item in candidates)
    difficulty = Counter(str(item.get("metadata", {}).get("difficulty", "UNKNOWN")) for item in candidates)
    incidents = Counter(str(item.get("metadata", {}).get("incident_family", "UNKNOWN")) for item in candidates)
    validation = validate_dataset(base / "data" / "training" / "candidates", "auto", validation_mode="governance") if candidates else None
    content = json.dumps(candidates, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return {
        "dataset_id": "smartops-candidate-pool",
        "dataset_version": "v0.1",
        "dataset_role": "CANDIDATE_POOL",
        "schema_version": "1.0.0",
        "content_hash": hashlib.sha256(content).hexdigest() if candidates else None,
        "counts": {"total": len(candidates), "valid": validation.valid if validation else 0, "invalid": validation.invalid if validation else 0, "duplicate": validation.duplicates if validation else 0, "unsafe": validation.unsafe if validation else 0, "approved": states.get("APPROVED", 0), "review_pending": states.get("REVIEW_PENDING", 0), "golden_derived": len(golden)},
        "source_distribution": dict(source),
        "difficulty_distribution": dict(difficulty),
        "incident_distribution": dict(incidents),
        "roles": {"training": "NOT_READY", "validation": "NOT_READY", "test": "NOT_READY", "golden": "NOT_READY", "regression": "NOT_READY"},
        "safety": "NOT_RUN",
        "leakage": "NOT_RUN",
        "independent_golden": "NOT_READY" if golden else "NOT_RUN",
        "derived_golden_policy": "NOT_INDEPENDENT",
        "limitations": ["Candidate records are not Approved training data.", "The existing Golden file is derived from candidates and cannot be used as an independent formal test set."],
    }


def write_report(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    out = base / "reports" / "phase-7.4"
    out.mkdir(parents=True, exist_ok=True)
    report = build_report(base)
    (out / "dataset-quality.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# Phase 7.4 Dataset Quality", "", "| Field | Value |", "|---|---|"]
    for key, value in report["counts"].items():
        lines.append(f"| {key} | {value} |")
    lines += ["", f"- Safety: **{report['safety']}**", f"- Leakage: **{report['leakage']}**", f"- Independent Golden: **{report['independent_golden']}**", "", "The existing Golden set remains NOT_INDEPENDENT."]
    (out / "dataset-quality.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


__all__ = ["build_report", "write_report"]


if __name__ == "__main__":
    print(json.dumps(write_report(), ensure_ascii=False, indent=2))
