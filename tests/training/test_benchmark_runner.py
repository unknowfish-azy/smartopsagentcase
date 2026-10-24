from training.benchmark_runner import BenchmarkRunner, summarize_observed


def test_benchmark_without_model_is_not_run():
    report = BenchmarkRunner().run([{"sample_id": "x"}])
    assert report["status"] == "NOT RUN"
    assert all(value is None for value in report["metrics"].values())


def test_observed_results_compute_metrics_without_fabrication():
    report = summarize_observed([
        {
            "task_success": True, "evidence_correct": True, "tool_correct": True,
            "risk_correct": True, "approval_correct": True, "verification_success": True,
            "unsupported_claim": False, "false_success": False, "safety_violation": False,
            "inspector_tp": 1, "inspector_fp": 0, "inspector_fn": 1,
            "latency_ms": 100, "token_cost": 12,
        },
        {
            "task_success": False, "evidence_correct": False, "tool_correct": False,
            "risk_correct": True, "approval_correct": False, "verification_success": False,
            "unsupported_claim": True, "false_success": True, "safety_violation": True,
            "inspector_tp": 0, "inspector_fp": 1, "inspector_fn": 0,
            "latency_ms": 200, "token_cost": 8,
        },
    ])
    assert report["status"] == "COMPLETED"
    assert report["sample_count"] == 2
    assert report["metrics"]["task_success"] == 0.5
    assert report["metrics"]["inspector_precision"] == 0.5
    assert report["metrics"]["inspector_recall"] == 0.5
    assert report["metrics"]["latency"] == 150
    assert report["metrics"]["token_cost"] == 20
