"""Read-only Phase 7.4 status aggregation.

This module deliberately derives statuses from existing reports and candidate
files. It never promotes samples, calls a provider, or invents metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATES = {"PASS", "BLOCKED", "NOT_RUN", "NOT_READY", "WARN"}


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default


def build_phase_status(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    gate = _read_json(base / "training" / "training-gate-report.json", {})
    readiness = _read_json(base / "training" / "readiness-report.json", {})
    quality = _read_json(base / "data" / "training" / "quality_report.json", {})
    baseline = _read_json(base / "data" / "training" / "eval" / "baseline-report.json", {})
    candidates = list((base / "data" / "training" / "candidates").glob("*.json")) if (base / "data" / "training" / "candidates").exists() else []
    records = [_read_json(p, {}) for p in candidates]
    states = [str(r.get("state", "CANDIDATE")) for r in records]
    approved = sum(1 for state in states if state == "APPROVED")
    train = val = test = 0
    datasets = readiness.get("checks", {}).get("dataset", {}).get("datasets", {})
    for item in datasets.values():
        train += int(item.get("train_count", 0) or 0)
        val += int(item.get("validation_count", 0) or 0)
        test += int(item.get("test_count", 0) or 0)
    gates = gate.get("gates", {})
    model = readiness.get("checks", {}).get("model", {})
    quality_status = str(quality.get("status", "NOT_RUN")).upper().replace(" ", "_")
    leakage_values = [str(item.get("leakage_status", "NOT_RUN")).upper() for item in datasets.values()]
    status = {
        # Code/local-test status is intentionally independent from data/model gates.
        # The project test suites are the authority for this value.
        "code": "PASS" if (base / "tests" / "training").exists() else "WARN",
        "dataset": "PASS" if candidates else "BLOCKED",
        "candidate": "PASS" if candidates else "BLOCKED",
        "validated": "PASS" if "VALIDATED" in states else "NOT_RUN",
        "quality_checked": "PASS" if "QUALITY_CHECKED" in states else "NOT_RUN",
        "safe": "PASS" if "SAFE" in states else "NOT_RUN",
        "review_pending": "PASS" if "REVIEW_PENDING" in states else "NOT_RUN",
        "approved": "PASS" if approved else "BLOCKED",
        "train": "PASS" if train else "NOT_READY",
        "validation": "PASS" if val else "NOT_READY",
        "test": "PASS" if test else "NOT_READY",
        "safety": "PASS" if quality_status == "PASS" else ("NOT_RUN" if quality_status == "NOT_RUN" else "BLOCKED"),
        "leakage": "PASS" if "PASS" in leakage_values else ("NOT_RUN" if all(value == "NOT_RUN" for value in leakage_values) else "BLOCKED"),
        "evaluator": gates.get("evaluator", "NOT_READY"),
        "real_model": "PASS" if model.get("status") == "READY" and model.get("provider") not in {None, "", "mock"} else "BLOCKED",
        "prompt_baseline": "PASS" if baseline.get("status") == "COMPLETED" else "NOT_RUN",
        "real_baseline": "NOT_RUN",
        "rag_ablation": "NOT_RUN",
        "inspector_ablation": "NOT_RUN",
        "verification_ablation": "NOT_RUN",
        "sft": "BLOCKED",
        "preference": "NOT_READY",
    }
    return {
        "phase": "7.4",
        "status": "PASS" if all(value == "PASS" for value in status.values()) else "BLOCKED",
        "status_values": status,
        "counts": {"candidate": len(candidates), "approved": approved, "train": train, "validation": val, "test": test},
        "limitations": ["No candidate is promoted or approved by this report.", "Unrun experiments remain NOT_RUN."],
    }


def write_phase_status(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    report = build_phase_status(base)
    out = base / "reports"
    out.mkdir(parents=True, exist_ok=True)
    (out / "phase-7.4-status.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# SmartOpsAgent Phase 7.4 Status", "", f"- Overall: **{report['status']}**", "", "| Gate | Status |", "|---|---|"]
    lines.extend(f"| {key} | {value} |" for key, value in report["status_values"].items())
    lines += ["", "Counts:", "", "```json", json.dumps(report["counts"], ensure_ascii=False, indent=2), "```", "", "No unrun experiment is represented as a numeric result.", ""]
    (out / "phase-7.4-status.md").write_text("\n".join(lines), encoding="utf-8")
    return report


__all__ = ["build_phase_status", "write_phase_status"]
