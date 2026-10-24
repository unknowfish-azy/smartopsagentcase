"""Rule/SOP baseline preflight and dry-run contract.

It does not claim model performance. A formal run requires an independent
Golden set and an approved evaluation role.
"""

from __future__ import annotations

import json
from pathlib import Path


def run(root: str | Path = ".") -> dict:
    base = Path(root)
    report = json.loads((base / "reports" / "phase-7.4" / "dataset-quality.json").read_text(encoding="utf-8")) if (base / "reports" / "phase-7.4" / "dataset-quality.json").exists() else {}
    independent = report.get("independent_golden") == "PASS"
    return {"baseline_id": "B0_RULE_SOP", "status": "NOT_RUN" if not independent else "READY", "is_model": False, "metrics": None, "reason": "Independent Golden and approved evaluation role are required before a formal Rule/SOP baseline."}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
