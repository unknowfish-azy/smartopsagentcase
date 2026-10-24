"""Conservative preflight for Prompt/Real Baseline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from training.readiness.model_check import check_model


def build_preflight(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    quality = json.loads((base / "reports" / "phase-7.4" / "dataset-quality.json").read_text(encoding="utf-8")) if (base / "reports" / "phase-7.4" / "dataset-quality.json").exists() else {}
    model = check_model()
    checks = {
        "approved_dataset": "PASS" if quality.get("counts", {}).get("approved", 0) > 0 else "BLOCKED",
        "split": "PASS" if all(quality.get("roles", {}).get(role) == "READY" for role in ("training", "validation", "test")) else "BLOCKED",
        "safety": quality.get("safety", "NOT_RUN"),
        "leakage": quality.get("leakage", "NOT_RUN"),
        "independent_golden": quality.get("independent_golden", "NOT_READY"),
        "evaluator": "READY" if (base / "data" / "evaluation" / "prompt-baseline" / "evaluator-dry-run.json").exists() else "BLOCKED",
        "real_agent": "READY" if model.get("status") == "READY" and model.get("provider") != "mock" else "BLOCKED",
    }
    return {"status": "PASS" if all(value in {"PASS", "READY"} for value in checks.values()) else "BLOCKED", "checks": checks, "reason": "All dataset, evaluator, independent Golden and REAL Agent checks are required."}


def write_preflight(root: str | Path = ".") -> dict[str, Any]:
    base = Path(root)
    report = build_preflight(base)
    out = base / "reports" / "phase-7.4"
    out.mkdir(parents=True, exist_ok=True)
    (out / "baseline-preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(write_preflight(), ensure_ascii=False, indent=2))
