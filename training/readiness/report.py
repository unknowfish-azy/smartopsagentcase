"""Serialize readiness results without secrets."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def overall_status(checks: dict[str, dict[str, Any]]) -> str:
    if any(value.get("status") == "BLOCKED" for value in checks.values()):
        return "BLOCKED"
    if any(value.get("status") == "PARTIAL" for value in checks.values()):
        return "PARTIAL"
    return "READY"


def build_report(checks: dict[str, dict[str, Any]]) -> dict[str, Any]:
    dataset = checks["dataset"]
    model = checks["model"]
    return {
        "status": overall_status(checks),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "gates": {
            "dataset": dataset["status"],
            "model": model["status"],
            "evaluation": "READY",
            "sft": "READY" if dataset["status"] == "READY" and model["status"] == "READY" else "BLOCKED",
            "preference_optimization": "NOT_READY",
        },
        "training_started": False,
        "secrets_included": False,
    }


def write_reports(report: dict[str, Any], json_path: str | Path, markdown_path: str | Path) -> None:
    json_file = Path(json_path)
    json_file.parent.mkdir(parents=True, exist_ok=True)
    json_file.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# SmartOpsAgent Training Readiness Report",
        "",
        f"- Status: **{report['status']}**",
        f"- Created: `{report['created_at']}`",
        "- Training started: `NO`",
        "- Secrets included: `NO`",
        "",
        "## Checks",
        "",
        "| Check | Status | Reason |",
        "|---|---|---|",
    ]
    for name, value in report["checks"].items():
        lines.append(f"| {name} | {value.get('status')} | {value.get('reason', '')} |")
    lines += ["", "## Gates", "", "| Gate | Status |", "|---|---|"]
    lines.extend(f"| {name} | {status} |" for name, status in report["gates"].items())
    lines += ["", "`BLOCKED`, `PARTIAL`, `NOT_READY` and `NOT RUN` are truthful environment states; no metric or training result is inferred.", ""]
    Path(markdown_path).write_text("\n".join(lines), encoding="utf-8")
