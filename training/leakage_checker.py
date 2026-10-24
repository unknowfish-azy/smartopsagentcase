"""Leakage checks for grouped SmartOps datasets."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from typing import Any


def _canonical(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tokens(record: dict[str, Any]) -> set[str]:
    text = _canonical(record).lower()
    return set(re.findall(r"[a-z0-9\u4e00-\u9fff]+", text))


def check_leakage(splits: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Return a report; this function never hides or mutates offending records."""
    report: dict[str, Any] = {
        "status": "PASS",
        "exact_duplicate": [],
        "near_duplicate": [],
        "scenario_duplicate": [],
        "evidence_duplicate": [],
        "root_cause_leakage": [],
        "environment_leakage": [],
        "version_leakage": [],
    }
    indexed: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for split_name, records in splits.items():
        if split_name not in {"train", "validation", "test"}:
            continue
        for record in records:
            sample_id = str(record.get("sample_id", "<missing>"))
            digest = hashlib.sha256(_canonical(record).encode("utf-8")).hexdigest()
            indexed["exact"][digest].append(f"{split_name}:{sample_id}")
            metadata = record.get("metadata", {})
            environment = record.get("environment", {})
            evidence = tuple(sorted(item.get("evidence_id", "") for item in record.get("evidence", []) if isinstance(item, dict)))
            indexed["scenario"][str(metadata.get("scenario_id", ""))].append(f"{split_name}:{sample_id}")
            indexed["root_cause"][str(metadata.get("root_cause_group", ""))].append(f"{split_name}:{sample_id}")
            indexed["environment"][str(environment.get("environment_id", ""))].append(f"{split_name}:{sample_id}")
            indexed["version"][str(environment.get("version", metadata.get("version", "")))].append(f"{split_name}:{sample_id}")
            indexed["evidence"][json.dumps(evidence)].append(f"{split_name}:{sample_id}")
            indexed["tokens"][sample_id] = list(_tokens(record))

    for digest, locations in indexed["exact"].items():
        if len({item.split(":", 1)[0] for item in locations}) > 1:
            report["exact_duplicate"].append({"hash": digest, "locations": locations})
    for key, locations in indexed["scenario"].items():
        if key and len({item.split(":", 1)[0] for item in locations}) > 1:
            report["scenario_duplicate"].append({"key": key, "locations": locations})
    for key, locations in indexed["evidence"].items():
        if key != "[]" and len({item.split(":", 1)[0] for item in locations}) > 1:
            report["evidence_duplicate"].append({"key": key, "locations": locations})
    for field, report_key in (("root_cause", "root_cause_leakage"), ("environment", "environment_leakage"), ("version", "version_leakage")):
        for key, locations in indexed[field].items():
            if key and len({item.split(":", 1)[0] for item in locations}) > 1:
                report[report_key].append({"key": key, "locations": locations})

    report["status"] = "LEAKAGE_DETECTED" if any(report[key] for key in report if key != "status") else "PASS"
    return report


__all__ = ["check_leakage"]
