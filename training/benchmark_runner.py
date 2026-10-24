"""Benchmark execution boundary for observed SmartOps model results."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Callable

from training.evaluation_runner import METRICS, not_run_report


def summarize_observed(results: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Compute metrics only from explicitly observed, labeled result records."""
    rows = list(results)
    if not rows:
        return not_run_report("no observed benchmark results")

    def rate(predicate: Callable[[dict[str, Any]], bool]) -> float | None:
        values = [predicate(row) for row in rows if predicate(row) is not None]
        return sum(values) / len(values) if values else None

    task = rate(lambda row: row.get("task_success") is True)
    evidence = rate(lambda row: row.get("evidence_correct") is True)
    tool = rate(lambda row: row.get("tool_correct") is True)
    risk = rate(lambda row: row.get("risk_correct") is True)
    approval = rate(lambda row: row.get("approval_correct") is True)
    verification = rate(lambda row: row.get("verification_success") is True)
    hallucination = rate(lambda row: row.get("unsupported_claim") is True)
    false_success = rate(lambda row: row.get("false_success") is True)
    safety = rate(lambda row: row.get("safety_violation") is True)
    inspector_tp = sum(row.get("inspector_tp", 0) for row in rows)
    inspector_fp = sum(row.get("inspector_fp", 0) for row in rows)
    inspector_fn = sum(row.get("inspector_fn", 0) for row in rows)
    latency = [row["latency_ms"] for row in rows if isinstance(row.get("latency_ms"), (int, float))]
    tokens = [row["token_cost"] for row in rows if isinstance(row.get("token_cost"), (int, float))]
    metrics = {name: None for name in METRICS}
    metrics.update({
        "task_success": task,
        "evidence_accuracy": evidence,
        "tool_accuracy": tool,
        "risk_accuracy": risk,
        "approval_accuracy": approval,
        "verification_success": verification,
        "hallucination_rate": hallucination,
        "false_success_rate": false_success,
        "safety_violation_rate": safety,
        "inspector_precision": inspector_tp / (inspector_tp + inspector_fp) if inspector_tp + inspector_fp else None,
        "inspector_recall": inspector_tp / (inspector_tp + inspector_fn) if inspector_tp + inspector_fn else None,
        "latency": sum(latency) / len(latency) if latency else None,
        "token_cost": sum(tokens) if tokens else None,
    })
    return {"status": "COMPLETED", "sample_count": len(rows), "metrics": metrics}


class BenchmarkRunner:
    """Run a supplied evaluator; no evaluator means an honest NOT RUN result."""

    def __init__(self, evaluator: Callable[[dict[str, Any]], dict[str, Any]] | None = None):
        self.evaluator = evaluator

    def run(self, dataset: Iterable[dict[str, Any]]) -> dict[str, Any]:
        if self.evaluator is None:
            return not_run_report("no model evaluator configured")
        observed = [self.evaluator(sample) for sample in dataset]
        return summarize_observed(observed)


__all__ = ["BenchmarkRunner", "summarize_observed"]
