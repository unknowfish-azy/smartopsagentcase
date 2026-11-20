"""Agent SLO 故障注入基准：指标、门禁与报表契约测试。"""

from __future__ import annotations

import json

import pytest

from scripts.eval_agent_slo import (
    SCENARIOS,
    percentile,
    ratio,
    render_markdown,
    run_benchmark,
    write_reports,
)

pytestmark = pytest.mark.agent


@pytest.fixture(scope="module")
def report():
    return run_benchmark(2)


def test_fixed_scenarios_produce_traceable_quantitative_evidence(report):
    assert report["status"] == "PASS"
    assert report["benchmark"]["scenario_count"] == 7
    assert report["benchmark"]["run_count"] == 14
    assert len(report["observations"]) == 14
    assert set(report["scenarios"]) == set(SCENARIOS)
    assert all(gate["status"] == "PASS" for gate in report["gates"])

    metrics = report["metrics"]
    assert metrics["scenario_conformance_rate"] == 1.0
    assert metrics["clean_dag_task_success_rate"] == 1.0
    assert metrics["downstream_skip_rate"] == 1.0
    assert metrics["timeout_detection_rate"] == 1.0
    assert metrics["independent_peer_success_rate"] == 1.0
    assert metrics["retry_recovery_rate"] == 1.0
    assert metrics["upstream_injection_rate"] == 1.0
    assert metrics["duplicate_block_rate"] == 1.0
    assert metrics["duplicate_call_avoidance_rate"] == 0.5
    assert metrics["orchestration_trace_coverage"] == 1.0
    assert metrics["retry_budget_violations"] == 0

    duplicate = report["scenarios"]["react_duplicate_guard"]
    assert duplicate["runs"] == 2
    assert duplicate["tool_calls"] == 2
    assert duplicate["duplicate_calls"] == 2
    assert duplicate["actual_tool_calls"] == 2

    # 每次运行都保留原始断言、延迟与样本序号；DAG 运行另保留 trace。
    for observation in report["observations"]:
        assert observation["passed"] is True
        assert observation["failures"] == []
        assert observation["duration_ms"] >= 0
        assert 1 <= observation["repetition"] <= 2
        if observation["family"] == "orchestration":
            assert observation["trace_id"]
            assert observation["waves"] == 4


def test_latency_percentiles_and_zero_denominator_contract():
    values = [10.0, 20.0, 30.0, 40.0]
    assert percentile(values, 0.50) == 25.0
    assert percentile(values, 0.95) == 38.5
    assert percentile(values, 0.99) == 39.7
    assert percentile([], 0.95) is None
    assert ratio(0, 0) is None
    assert ratio(1, 4) == 0.25


def test_latency_budget_failure_closes_gate():
    # 0.001ms 是故意不可能达到的调度预算，用于验证门禁不会只报不拦。
    failed = run_benchmark(1, clean_p95_budget_ms=0.001)
    gate = next(g for g in failed["gates"] if g["gate_id"] == "clean_dag_p95_overhead")
    assert failed["status"] == "FAIL"
    assert gate["status"] == "FAIL"


def test_json_and_markdown_reports_keep_measurement_boundary(report, tmp_path):
    json_path = tmp_path / "nested" / "agent_slo.json"
    markdown_path = tmp_path / "nested" / "agent_slo.md"
    write_reports(report, json_path, markdown_path)

    persisted = json.loads(json_path.read_text(encoding="utf-8"))
    assert persisted["benchmark"]["production_observation"] is False
    assert persisted["benchmark"]["real_model_invoked"] is False
    assert persisted["benchmark"]["external_calls"] is False
    assert len(persisted["observations"]) == 14

    markdown = markdown_path.read_text(encoding="utf-8")
    assert markdown == render_markdown(report)
    assert "确定性故障注入基准" in markdown
    assert "不是生产模型或 API 延迟" in markdown
    assert "P50 / P95 / P99" in markdown
    assert "门禁结论：**PASS**" in markdown
    for scenario in SCENARIOS:
        assert f"`{scenario}`" in markdown
