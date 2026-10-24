"""Convert traceable incident records into role-specific candidate datasets.

Builders preserve provenance and keep quality status pending. They do not write
files, train models, or promote synthetic records automatically.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _base(record: dict[str, Any], dataset_type: str, task_type: str, instruction: str) -> dict[str, Any]:
    result = deepcopy(record)
    result["dataset_type"] = dataset_type
    result["task_type"] = task_type
    result["instruction"] = instruction
    result["quality"] = {"status": "PENDING", "human_review": "NOT_REVIEWED", "checks": {}}
    return result


def to_sft(record: dict[str, Any]) -> dict[str, Any]:
    """Build an Ops Reasoner SFT candidate from an incident record."""
    result = _base(record, "SFT", "OPS_REASONING", record["instruction"])
    result["expected_behavior"] = {"evidence_first": True, "read_only_first": True}
    return result


def to_preference(record: dict[str, Any]) -> dict[str, Any]:
    """Build a chosen/rejected candidate without exposing hidden reasoning."""
    result = _base(record, "PREFERENCE", "PREFERENCE_RANKING", record["instruction"])
    chosen = {
        "reasoning_summary": record["output"].get("reasoning_summary", ""),
        "plan": record["output"].get("plan", []),
        "next_tool": record["output"].get("next_tool"),
        "risk": record["output"].get("risk"),
        "approval_required": record["output"].get("approval_required"),
        "verification_plan": record["output"].get("verification_plan", []),
    }
    rejected = {
        "reasoning_summary": "立即执行状态变更，未先收集证据。",
        "next_tool": (record.get("expected_behavior", {}).get("forbidden_tools") or ["state.change"])[0],
        "risk": "LOW",
        "approval_required": False,
    }
    result["expected_behavior"] = {
        "chosen": chosen,
        "rejected": rejected,
        "reason": "Evidence First, Read-only First, Risk Controlled and Verification Required",
        "principles": ["EVIDENCE_FIRST", "READ_ONLY_FIRST", "RISK_CONTROLLED", "VERIFICATION_REQUIRED"],
    }
    result["output"] = {
        "chosen": chosen,
        "rejected": rejected,
        "reason": "Evidence First, Read-only First, Risk Controlled and Verification Required",
        "principles": ["EVIDENCE_FIRST", "READ_ONLY_FIRST", "RISK_CONTROLLED", "VERIFICATION_REQUIRED"],
    }
    return result


def to_evidence(record: dict[str, Any]) -> dict[str, Any]:
    """Build one Evidence Verifier candidate with claim/evidence relation."""
    result = _base(record, "EVIDENCE", "EVIDENCE_VERIFICATION", record["instruction"])
    result["output"] = {
        "label": "PARTIALLY_SUPPORTED" if record["metadata"].get("difficulty") == "HARD" else "SUPPORTED",
        "reason": "Synthetic evidence relation requires later human review.",
        "supporting_evidence": [item["evidence_id"] for item in record.get("evidence", [])],
        "confidence": record["output"].get("confidence", 0.0),
    }
    result["expected_behavior"] = {"claim": record["output"].get("diagnosis", "UNKNOWN")}
    return result


def to_inspector(record: dict[str, Any]) -> dict[str, Any]:
    """Build an Inspector Judge candidate from the same traceable incident."""
    result = _base(record, "INSPECTOR", "INSPECTION", record["instruction"])
    difficult = record["metadata"].get("difficulty") == "HARD"
    result["output"] = {
        "decision": "WARNING" if difficult else "PASS",
        "category": "EVIDENCE" if difficult else "TOOL",
        "severity": "WARNING" if difficult else "INFO",
        "issues": ([{"category": "EVIDENCE", "reason": "Conflicting evidence"}] if difficult else []),
        "reason": "Synthetic candidate; requires Inspector and human review.",
        "recommendation": "Collect additional read-only evidence before state change.",
        "requires_human": difficult,
    }
    result["expected_behavior"] = {"decision": result["output"]["decision"]}
    return result


__all__ = ["to_evidence", "to_inspector", "to_preference", "to_sft"]
