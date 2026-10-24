from training.dataset_splitter import split_grouped
from training.leakage_checker import check_leakage


def record(scenario, root, environment, version="1.0"):
    return {
        "sample_id": scenario,
        "metadata": {"scenario_id": scenario, "incident_family": root, "root_cause_group": root, "version": version},
        "environment": {"environment_id": environment, "version": version},
        "evidence": [{"evidence_id": f"ev-{scenario}"}],
    }


def test_grouped_split_keeps_scenarios_together_and_is_deterministic():
    records = [record(f"s{i}", f"root{i}", f"env{i}") for i in range(10)]
    first = split_grouped(records, strategy="scenario", train_ratio=0.6, validation_ratio=0.2)
    second = split_grouped(records, strategy="scenario", train_ratio=0.6, validation_ratio=0.2)
    assert first == second
    assert sorted(sum((part for name, part in first.items() if name != "strategy"), []), key=lambda item: item["sample_id"]) == records


def test_leakage_report_detects_scenario_and_evidence_cross_split():
    shared_a = record("same", "root-a", "env-a")
    shared_b = record("same", "root-a", "env-b")
    report = check_leakage({"train": [shared_a], "validation": [shared_b], "test": []})
    assert report["status"] == "LEAKAGE_DETECTED"
    assert report["scenario_duplicate"]
    assert report["evidence_duplicate"]
    assert report["root_cause_leakage"]


def test_clean_grouped_splits_have_no_leakage():
    report = check_leakage({
        "train": [record("train", "root-train", "env-train", "1.0")],
        "validation": [record("val", "root-val", "env-val", "2.0")],
        "test": [record("test", "root-test", "env-test", "3.0")],
    })
    assert report["status"] == "PASS"
