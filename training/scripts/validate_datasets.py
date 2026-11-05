"""Run the current dataset quality gate and write truthful control-plane reports."""

from __future__ import annotations

import json
from pathlib import Path

from training.baseline_runner import baseline_not_run
from training.manifest import write_manifests


def main() -> int:
    root = Path(__file__).resolve().parents[2] / "data" / "training"
    manifests = write_manifests(root)
    quality = {
        "status": "NOT_RUN" if not any(item["sample_count"] for item in manifests.values()) else "COMPLETED",
        "reason": "No promoted samples exist" if not any(item["sample_count"] for item in manifests.values()) else "Validated promoted samples",
        "schema_version": "1.0.0",
        "safety_status": "NOT_RUN",
        "leakage_status": "NOT_RUN",
        "safety_report": None,
        "leakage_report": None,
        "datasets": manifests,
    }
    (root / "quality_report.json").write_text(json.dumps(quality, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (root / "eval" / "baseline-report.json").write_text(
        json.dumps(baseline_not_run("no configured real model, approved dataset or evaluator"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"quality": quality["status"], "datasets": len(manifests), "baseline": "NOT_RUN"}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
