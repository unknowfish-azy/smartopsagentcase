"""Explicit, single-sample human review CLI.

Candidate JSON files live under ``data/training/candidates``. This command
never bulk-approves and requires a reviewer for every state-changing action.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.candidate_lifecycle import HumanReview, TrainingCandidate


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load(root: Path, sample_id: str) -> tuple[Path, dict[str, Any]]:
    folder = root / "data" / "training" / "candidates"
    for path in folder.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if record.get("sample_id") == sample_id:
            return path, record
    raise SystemExit(f"candidate not found: {sample_id}")


def _list(root: Path) -> None:
    folder = root / "data" / "training" / "candidates"
    rows = []
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            rows.append({"sample_id": record.get("sample_id"), "state": record.get("state", "CANDIDATE"), "source_type": record.get("source", {}).get("source_type", record.get("source_type"))})
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
    print(json.dumps(rows, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review one training candidate")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true")
    group.add_argument("--sample")
    group.add_argument("--approve")
    group.add_argument("--reject")
    group.add_argument("--modify")
    parser.add_argument("--reviewer", help="human reviewer identifier")
    parser.add_argument("--reason", default="")
    args = parser.parse_args(argv)
    root = _root()
    if args.list:
        _list(root)
        return 0
    sample_id = args.sample or args.approve or args.reject or args.modify
    if args.sample:
        _, record = _load(root, sample_id)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0
    if not args.reviewer or not args.reason:
        parser.error("--reviewer and --reason are required for review actions")
    path, record = _load(root, sample_id)
    state = record.get("state", "CANDIDATE")
    candidate = TrainingCandidate(record, state=state, history=record.get("history", [state]))
    if candidate.review:
        # Stored reviews are plain JSON; review changes still require explicit CLI input.
        candidate.review = None
    if state == "SAFE":
        candidate.transition("REVIEW_PENDING")
    elif state != "REVIEW_PENDING":
        raise SystemExit(f"candidate must be SAFE or REVIEW_PENDING, got {state}")
    action = "APPROVED" if args.approve else "REJECTED" if args.reject else "MODIFIED"
    review = HumanReview(f"review-{sample_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}", sample_id, args.reviewer, action, args.reason)
    candidate.submit_review(review)
    record["state"] = candidate.state
    record["history"] = candidate.history
    record["review"] = {"review_id": review.review_id, "sample_id": sample_id, "reviewer": review.reviewer, "status": review.status, "reason": review.reason, "created_at": review.created_at, "updated_at": review.updated_at}
    if action == "APPROVED":
        record.setdefault("quality", {})["human_review"] = "APPROVED"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"sample_id": sample_id, "state": candidate.state, "review_status": action}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
