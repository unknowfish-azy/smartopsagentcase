"""Ground-truth evaluator primitives for structured agent outputs.

It is intentionally rule-based and conservative: missing predictions or labels
are reported as NOT_RUN rather than treated as failures or successes.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from training.evaluation_runner import METRICS


def metric(correct: int | None, total: int | None, *, status: str | None = None) -> dict[str, Any]:
    if correct is None or total is None or total <= 0:
        return {"correct": None, "total": None, "value": None, "status": status or "NOT_RUN"}
    return {"correct": correct, "total": total, "value": correct / total, "status": status or "COMPLETED"}


def evaluate_cases(cases: Iterable[dict[str, Any]], prediction_key: str = "prediction") -> dict[str, Any]:
    cases = list(cases)
    if not cases:
        return {"status": "NOT_RUN", "metrics": {name: metric(None, None) for name in METRICS}}
    fields: dict[str, Callable[[dict[str, Any], dict[str, Any]], bool]] = {
        "root_cause_accuracy": lambda expected, actual: expected.get("root_cause") == actual.get("root_cause"),
        "tool_accuracy": lambda expected, actual: expected.get("tool") == actual.get("tool") or expected.get("next_tool") == actual.get("next_tool"),
        "risk_accuracy": lambda expected, actual: expected.get("risk") == actual.get("risk"),
        "approval_accuracy": lambda expected, actual: expected.get("approval") == actual.get("approval") or expected.get("approval_required") == actual.get("approval_required"),
        "verification_success": lambda expected, actual: expected.get("verification") == actual.get("verification"),
        "task_success": lambda expected, actual: expected.get("result") == actual.get("result") or expected.get("task_success") == actual.get("task_success"),
    }
    metrics = {name: metric(None, None) for name in METRICS}
    for name, predicate in fields.items():
        comparable = [(case.get("ground_truth", {}), case.get(prediction_key)) for case in cases if isinstance(case.get("ground_truth"), dict) and isinstance(case.get(prediction_key), dict)]
        if comparable:
            correct = sum(1 for expected, actual in comparable if predicate(expected, actual))
            metrics[name] = metric(correct, len(comparable))
    executed = any(item["status"] == "COMPLETED" for item in metrics.values())
    return {"status": "COMPLETED" if executed else "NOT_RUN", "metrics": metrics}


__all__ = ["metric", "evaluate_cases"]
