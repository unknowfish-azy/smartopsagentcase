"""Annotate the existing candidate-derived Golden set as evaluation-only and non-independent."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def lock(root: str | Path = ".") -> dict:
    base = Path(root)
    path = base / "data" / "evaluation" / "prompt-baseline" / "golden-cases.json"
    if not path.exists():
        return {"status": "NOT_FOUND"}
    cases = json.loads(path.read_text(encoding="utf-8"))
    for case in cases:
        case["derived_from_candidate"] = True
        case["independence"] = "NOT_INDEPENDENT"
        case["evaluation_only"] = True
    content = json.dumps(cases, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(content).hexdigest()
    lock_record = {"dataset_id": "smartops-derived-golden", "dataset_version": "v0.1", "dataset_role": "GOLDEN", "schema_version": "1.0.0", "source_type": "DERIVED_CANDIDATE", "independence": "NOT_INDEPENDENT", "evaluation_only": True, "frozen": True, "content_hash": digest, "created_at": datetime.now(timezone.utc).isoformat(), "created_by": "phase-7.4-governance"}
    path.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (path.parent / "golden-manifest.json").write_text(json.dumps(lock_record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return lock_record


if __name__ == "__main__":
    print(json.dumps(lock(), ensure_ascii=False, indent=2))
