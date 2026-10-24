"""Build fixed, non-model Golden Cases from candidate ground truth."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def build(root: str | Path = ".", limit: int = 40) -> int:
    base = Path(root)
    candidates = sorted((base / "data" / "training" / "candidates").glob("*.json"))[:limit]
    if not candidates:
        raise ValueError("candidate dataset is empty")
    output = base / "data" / "evaluation" / "prompt-baseline"
    output.mkdir(parents=True, exist_ok=True)
    cases = []
    for path in candidates:
        record = json.loads(path.read_text(encoding="utf-8"))
        expected = record["output"]
        cases.append({
            "case_id": f"golden-{record['sample_id']}",
            "input": {"instruction": record["instruction"], "task_type": record["task_type"]},
            "environment": record["environment"],
            "knowledge": record["knowledge"],
            "evidence": record["evidence"],
            "expected_root_cause": expected.get("root_cause"),
            "expected_action": expected.get("plan"),
            "expected_tool": expected.get("next_tool"),
            "expected_tool_arguments": {},
            "expected_risk": expected.get("risk"),
            "expected_approval": expected.get("approval_required"),
            "expected_verification": record["verification"],
            "expected_inspection": record["inspector"],
            "ground_truth": {
                "root_cause": expected.get("root_cause"),
                "tool": expected.get("next_tool"),
                "risk": expected.get("risk"),
                "approval": expected.get("approval_required"),
                "verification": record["verification"].get("status"),
                "result": expected.get("root_cause"),
            },
            "source_ref": record["source"].get("source_ref"),
            "ground_truth_locked": True,
        })
    target = output / "golden-cases.json"
    target.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(cases)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--limit", type=int, default=40)
    args = parser.parse_args()
    print(json.dumps({"created": build(args.root, args.limit), "ground_truth_locked": True, "model_called": False}, ensure_ascii=False))
