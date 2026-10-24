"""Build the Phase 6 training gate report from existing local reports.

This is a read-only gate summary: it never promotes data, calls a model, or
changes a registry state.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_gate_report(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    readiness = json.loads((base / "training" / "readiness-report.json").read_text(encoding="utf-8"))
    quality = json.loads((base / "data" / "training" / "quality_report.json").read_text(encoding="utf-8"))
    baseline = json.loads((base / "data" / "training" / "eval" / "baseline-report.json").read_text(encoding="utf-8"))
    dataset_check = readiness["checks"]["dataset"]
    approved = sum(item.get("approved_count", 0) for item in dataset_check["datasets"].values())
    split_ready = approved > 0 and any(
        item.get("train_count", 0) and item.get("validation_count", 0) and item.get("test_count", 0)
        for item in dataset_check["datasets"].values()
    )
    def canonical_status(value: object, default: str = "NOT_RUN") -> str:
        text = str(value if value is not None else default).upper().replace(" ", "_")
        return text or default

    gates = {
        "dataset": "READY" if approved > 0 else "BLOCKED",
        "approved_samples": "READY" if approved > 0 else "BLOCKED",
        "split": "READY" if split_ready else "BLOCKED",
        "leakage": "PASS" if split_ready and any(item.get("leakage_status") == "PASS" for item in dataset_check["datasets"].values()) else "BLOCKED",
        "safety": "PASS" if quality.get("safety_status") == "PASS" else "BLOCKED",
        "model": "READY" if readiness["checks"]["model"]["status"] == "READY" else "BLOCKED",
        "evaluator": "READY" if baseline.get("status") == "COMPLETED" else "BLOCKED",
        "baseline": "READY" if baseline.get("status") == "COMPLETED" else "BLOCKED",
        "dependencies": "READY" if readiness["checks"]["requirements"]["status"] == "READY" else "BLOCKED",
        "hardware": readiness["checks"]["hardware"]["status"],
    }
    required = ("dataset", "approved_samples", "split", "leakage", "safety", "model", "evaluator", "baseline", "dependencies")
    return {
        "status": "READY" if all(gates[name] in {"READY", "PASS"} for name in required) else "BLOCKED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "gates": gates,
        "approved_samples": approved,
        "training_allowed": False,
        "baseline_status": canonical_status(baseline.get("status")),
        "quality_status": canonical_status(quality.get("status")),
        "limitations": ["No sample promotion or model invocation is performed by this report."],
    }


def write_gate_report(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    report = build_gate_report(base)
    output = base / "training" / "training-gate-report.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = ["# SmartOpsAgent Training Gate Report", "", f"- Status: **{report['status']}**", f"- Approved samples: **{report['approved_samples']}**", "- Training allowed: **NO**", "", "| Gate | Status |", "|---|---|"]
    lines.extend(f"| {name} | {status} |" for name, status in report["gates"].items())
    lines.extend(["", "No data was promoted and no model was invoked by this report.", ""])
    (base / "training" / "training-gate-report.md").write_text("\n".join(lines), encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(write_gate_report(), ensure_ascii=False, indent=2))
