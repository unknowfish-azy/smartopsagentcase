"""Baseline evaluation boundary with explicit NOT RUN behavior."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from training.evaluation_runner import METRICS


def baseline_not_run(reason: str) -> dict[str, Any]:
    return {
        "experiment_id": "EXP-BASELINE-001",
        "status": "NOT RUN",
        "model": None,
        "dataset_version": None,
        "data_class": None,
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {name: None for name in METRICS},
    }


def run_baseline(*, model: str | None, dataset_version: str | None, evaluator: Any = None) -> dict[str, Any]:
    """A baseline requires a real model, approved dataset and evaluator."""
    if not model or not dataset_version or evaluator is None:
        return baseline_not_run("requires a configured model, approved dataset and evaluator")
    raise NotImplementedError("baseline execution adapter is not configured for this environment")


__all__ = ["baseline_not_run", "run_baseline"]
