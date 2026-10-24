"""Orchestrate readiness checks for the Phase 3 training gate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from training.readiness.dataset_check import check_datasets
from training.readiness.hardware_check import check_hardware
from training.readiness.model_check import check_model
from training.readiness.report import build_report, write_reports
from training.readiness.requirements_check import check_requirements


def run_readiness_check(project_root: str | Path = ".") -> dict[str, Any]:
    root = Path(project_root)
    checks = {
        "requirements": check_requirements(),
        "model": check_model(),
        "dataset": check_datasets(root / "data" / "training"),
        "hardware": check_hardware(root / "training" / "artifacts"),
    }
    report = build_report(checks)
    write_reports(report, root / "training" / "readiness-report.json", root / "training" / "readiness-report.md")
    return report


__all__ = ["run_readiness_check"]
