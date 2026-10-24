"""Generate a bounded, explicitly synthetic candidate catalog.

The command writes candidates only. It never changes review state to APPROVED
and never labels synthetic records as REAL.
"""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from training.synthetic_incidents import INCIDENT_DEFINITIONS, generate_incident


def generate(root: str | Path = ".", count: int = 40) -> int:
    if not 20 <= count <= 40:
        raise ValueError("count must be between 20 and 40")
    folder = Path(root) / "data" / "training" / "candidates"
    folder.mkdir(parents=True, exist_ok=True)
    scenario_kinds = (
        "normal", "service_unavailable", "configuration_error", "dependency_failure",
        "resource_pressure", "authentication_error", "permission_failure",
        "version_mismatch", "verification_failure", "evidence_insufficient",
        "conflicting_evidence", "approval_missing", "false_success", "tool_loop",
    )
    for index in range(count):
        family_index = index % len(INCIDENT_DEFINITIONS) + 1
        difficult = index % 2 == 1
        record = copy.deepcopy(generate_incident(family_index, difficult=difficult).to_dict())
        variant = index // len(INCIDENT_DEFINITIONS) + 1
        base_id = record["sample_id"]
        record["sample_id"] = f"candidate-{variant:02d}-{base_id}"
        record["scenario_id"] = f"{base_id}-variant-{variant:02d}"
        record["metadata"]["scenario_id"] = record["scenario_id"]
        record["metadata"]["difficulty"] = "HARD" if difficult else "STANDARD"
        record["metadata"]["scenario_kind"] = scenario_kinds[index % len(scenario_kinds)]
        record["metadata"]["source_type"] = "SYNTHETIC"
        record["environment"]["environment_id"] = f"synthetic-env-{variant:02d}-{family_index:03d}"
        for evidence in record["evidence"]:
            evidence["evidence_id"] = f"{record['sample_id']}-{evidence['evidence_id']}"
        record["state"] = "CANDIDATE"
        record["history"] = ["CANDIDATE"]
        record["review"] = {"status": "PENDING", "reviewer": None, "reason": "", "review_version": "1"}
        record["quality"]["human_review"] = "NOT_REVIEWED"
        record["quality"]["status"] = "PENDING"
        # The existing unified schema uses SYNTHETIC_INCIDENT as the source
        # enum while data_class carries the broader SYNTHETIC provenance.
        record["source"]["source_type"] = "SYNTHETIC_INCIDENT"
        record["source"]["source_ref"] = f"synthetic-candidate-catalog/{record['scenario_id']}"
        record["source"]["data_class"] = "SYNTHETIC"
        kind = record["metadata"]["scenario_kind"]
        if kind == "version_mismatch":
            record["environment"]["os"] = "Ubuntu 24.04 (synthetic)"
            record["knowledge"][0]["version"] = "ubuntu-22.04"
            record["output"]["diagnosis"] = "VERSION_MISMATCH"
            record["output"]["root_cause"] = "Environment and knowledge versions differ"
            record["output"]["reasoning_summary"] = "Version mismatch requires matching knowledge before action."
        elif kind == "permission_failure":
            record["policy"]["permission"] = "READ_ONLY"
            record["output"]["next_tool"] = record["expected_behavior"]["forbidden_tools"][0]
            record["output"]["diagnosis"] = "REJECTED"
            record["output"]["reasoning_summary"] = "Requested state change is not permitted by the read-only policy."
        elif kind == "approval_missing":
            record["output"]["risk"] = "HIGH"
            record["output"]["approval_required"] = True
            record["policy"]["state_change_requires_approval"] = True
            record["output"]["diagnosis"] = "BLOCKED"
        elif kind == "false_success":
            record["verification"] = {"status": "FAIL", "replan_required": True, "service_health": "FAIL"}
            record["output"]["diagnosis"] = "FALSE_SUCCESS"
            record["output"]["reasoning_summary"] = "Tool exit code is insufficient; health verification failed."
        elif kind == "tool_loop":
            record["agent_context"]["tool_history"] = [record["output"]["next_tool"]] * 3
            record["verification"] = {"status": "FAIL", "replan_required": True}
            record["output"]["diagnosis"] = "TOOL_LOOP"
        elif kind == "evidence_insufficient":
            record["evidence"] = [{
                "evidence_id": f"{record['sample_id']}-insufficient",
                "source": "synthetic/insufficient-observation",
                "content": "Available observation is insufficient to identify a root cause.",
                "timestamp": record["environment"]["observed_at"],
                "relevance": 0.1,
                "version": "synthetic-1",
                "support_relation": "UNKNOWN",
            }]
            record["output"]["diagnosis"] = "REQUEST_MORE_EVIDENCE"
            record["output"]["root_cause"] = "UNKNOWN"
            record["output"]["evidence"] = []
            record["output"]["confidence"] = 0.1
        (folder / f"{record['sample_id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    print(json.dumps({"created": generate(args.root, args.count), "source_type": "SYNTHETIC", "state": "CANDIDATE", "approved": 0}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
