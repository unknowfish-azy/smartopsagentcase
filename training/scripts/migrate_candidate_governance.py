"""Add deterministic Phase 7.4 governance metadata to existing candidates.

The migration derives fields only from existing scenario, source, environment,
and evidence values. It does not change labels, ground truth, or sample IDs.
"""

from __future__ import annotations

import json
import argparse
from pathlib import Path


DIFFICULTY = {
    "normal": "L1",
    "evidence_insufficient": "L2",
    "conflicting_evidence": "L4",
    "version_mismatch": "L5",
    "permission_failure": "L6",
    "approval_missing": "L6",
    "false_success": "L7",
    "tool_loop": "L8",
}


def migrate(root: str | Path = ".", *, check_only: bool = False) -> dict[str, int]:
    folder = Path(root) / "data" / "training" / "candidates"
    changed = 0
    missing = 0
    for path in sorted(folder.glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        metadata = record.setdefault("metadata", {})
        kind = str(metadata.get("scenario_kind", "")).lower()
        before = json.dumps(record, ensure_ascii=False, sort_keys=True)
        metadata.setdefault("difficulty_level", DIFFICULTY.get(kind, "L3"))
        metadata.setdefault("environment_family", str(record.get("environment", {}).get("environment_id", "UNKNOWN")).split("-env-", 1)[0])
        services = record.get("environment", {}).get("services", {})
        service = next(iter(services), "UNKNOWN")
        metadata.setdefault("version_family", str(services.get(service, {}).get("version", "UNKNOWN")))
        record.setdefault("dataset_role", "CANDIDATE_POOL")
        record.setdefault("source_reference", record.get("source", {}).get("source_ref"))
        record.setdefault("parent_sample_id", None)
        record.setdefault("created_at", record.get("source", {}).get("created_at"))
        record.setdefault("created_by", "phase-7.3-synthetic-candidate-generator")
        for index, evidence in enumerate(record.get("evidence", [])):
            if not isinstance(evidence, dict):
                continue
            relation = str(evidence.get("support_relation", "")).upper()
            status = "CONFLICTING" if kind == "conflicting_evidence" or relation in {"CONTRADICTED", "UNKNOWN"} else "DIRECT"
            if kind == "evidence_insufficient":
                status = "INSUFFICIENT"
            evidence.setdefault("document_id", evidence.get("source", "synthetic-document"))
            evidence.setdefault("chunk_id", evidence.get("evidence_id", f"{record['sample_id']}-chunk-{index}"))
            evidence.setdefault("confidence", evidence.get("relevance", 0.0))
            evidence.setdefault("evidence_status", status)
        after = json.dumps(record, ensure_ascii=False, sort_keys=True)
        if before != after:
            missing += 1
            if not check_only:
                path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                changed += 1
    return {"updated": changed, "would_update": missing if check_only else 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate or audit candidate governance metadata")
    parser.add_argument("--check", action="store_true", help="read-only audit; do not modify candidate files")
    args = parser.parse_args()
    print(json.dumps(migrate(check_only=args.check), ensure_ascii=False))
