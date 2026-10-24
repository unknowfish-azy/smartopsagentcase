"""Dataset readiness checks based on manifests, without promoting data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DATASET_TYPES = ("sft", "preference", "inspector", "evidence", "tool_call", "safety", "verification")


def check_datasets(root: str | Path) -> dict[str, Any]:
    base = Path(root)
    datasets: dict[str, Any] = {}
    for name in DATASET_TYPES:
        path = base / name / "manifest.json"
        if not path.exists():
            datasets[name] = {"status": "BLOCKED", "manifest": False, "approved_count": 0, "reason": "manifest missing"}
            continue
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            datasets[name] = {"status": "BLOCKED", "manifest": True, "approved_count": 0, "reason": f"invalid manifest: {exc}"}
            continue
        approved = int(manifest.get("approved_count", 0) or 0)
        sample_count = int(manifest.get("sample_count", 0) or 0)
        leakage = manifest.get("leakage_status") or ("NOT_RUN" if not manifest.get("leakage_report") else "UNKNOWN")
        ready = approved > 0 and manifest.get("status") == "READY" and leakage in {"PASS", "PASSED"}
        datasets[name] = {
            "status": "READY" if ready else "DRAFT",
            "manifest": True,
            "dataset_id": manifest.get("dataset_id"),
            "version": manifest.get("version"),
            "sample_count": sample_count,
            "approved_count": approved,
            "leakage_status": leakage,
            "reason": "approved samples and leakage pass required" if not ready else "dataset can enter training gate",
        }
    ready_count = sum(item["status"] == "READY" for item in datasets.values())
    return {
        "status": "READY" if ready_count else "BLOCKED",
        "ready_count": ready_count,
        "datasets": datasets,
        "reason": "at least one approved dataset passed readiness" if ready_count else "no dataset has approved samples and a passing leakage check",
    }
