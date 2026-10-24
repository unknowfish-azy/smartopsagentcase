"""File-oriented model registry records with honest lifecycle states."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


VALID_STATUSES = {"PLANNED", "TRAINING", "TRAINED", "FAILED", "NOT_RUN", "CANCELLED"}


def planned_model(
    *, model_version: str, base_model: str, dataset_version: str, training_config: dict[str, Any]
) -> dict[str, Any]:
    """Create a registry record that cannot imply training occurred."""
    if not model_version or not base_model or not dataset_version:
        raise ValueError("model_version, base_model and dataset_version are required")
    return {
        "model_version": model_version,
        "base_model": base_model,
        "dataset_version": dataset_version,
        "training_config": training_config,
        "evaluation": {"status": "NOT RUN", "metrics": {}},
        "status": "PLANNED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "artifact": None,
    }


def mark_trained(record: dict[str, Any], *, artifact: str, evaluation: dict[str, Any]) -> dict[str, Any]:
    """Allow TRAINED only with an artifact and completed evaluation evidence."""
    if not artifact or evaluation.get("status") != "COMPLETED":
        raise ValueError("TRAINED requires an artifact and COMPLETED evaluation")
    result = dict(record)
    result.update({"status": "TRAINED", "artifact": artifact, "evaluation": evaluation})
    return result


__all__ = ["VALID_STATUSES", "mark_trained", "planned_model"]
