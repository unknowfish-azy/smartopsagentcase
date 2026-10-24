"""Deterministic grouped train/validation/test splitting."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable


GROUP_FIELDS = {
    "incident": "incident_family",
    "root_cause": "root_cause_group",
    "environment": "environment_id",
    "version": "version",
    "scenario": "scenario_id",
}


def split_grouped(
    records: Iterable[dict[str, Any]],
    *,
    strategy: str = "incident",
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
) -> dict[str, list[dict[str, Any]]]:
    """Split whole groups deterministically; records from one group never straddle splits."""
    if strategy not in GROUP_FIELDS:
        raise ValueError(f"unsupported grouping strategy: {strategy}")
    if not 0 < train_ratio < 1 or not 0 <= validation_ratio < 1 or train_ratio + validation_ratio >= 1:
        raise ValueError("train_ratio and validation_ratio must leave a non-empty test split")
    field = GROUP_FIELDS[strategy]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = _group_value(record, field)
        groups[key].append(record)
    ordered = sorted(groups.items(), key=lambda item: item[0])
    total = len(ordered)
    train_count = max(1, int(total * train_ratio)) if total else 0
    validation_count = max(0, int(total * validation_ratio))
    if train_count + validation_count >= total and total:
        validation_count = max(0, total - train_count - 1)
    train_groups = ordered[:train_count]
    validation_groups = ordered[train_count:train_count + validation_count]
    test_groups = ordered[train_count + validation_count:]
    return {
        "train": [record for _, values in train_groups for record in values],
        "validation": [record for _, values in validation_groups for record in values],
        "test": [record for _, values in test_groups for record in values],
        "strategy": strategy,
    }


def _group_value(record: dict[str, Any], field: str) -> str:
    if field == "environment_id":
        value = record.get("environment", {}).get("environment_id")
    elif field == "version":
        value = record.get("environment", {}).get("version") or record.get("metadata", {}).get("version")
    else:
        value = record.get("metadata", {}).get(field)
    if value in (None, ""):
        raise ValueError(f"record missing grouping field: {field}")
    return str(value)


__all__ = ["GROUP_FIELDS", "split_grouped"]
