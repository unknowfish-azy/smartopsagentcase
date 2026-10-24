"""Evaluation plan builder. It never fabricates metric values."""

from __future__ import annotations

from datetime import datetime, timezone


METRICS = (
    "task_success", "root_cause_accuracy", "evidence_accuracy", "tool_accuracy",
    "risk_accuracy", "approval_accuracy", "verification_success",
    "inspector_precision", "inspector_recall", "hallucination_rate",
    "false_success_rate", "safety_violation_rate", "latency", "token_cost",
)


def not_run_report(reason: str = "evaluation has not been executed") -> dict:
    return {
        "status": "NOT RUN",
        "reason": reason,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {name: None for name in METRICS},
    }
