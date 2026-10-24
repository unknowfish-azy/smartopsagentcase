import json

from training.baseline_runner import run_baseline
from training.manifest import build_manifest


def test_empty_dataset_manifest_is_draft(tmp_path):
    (tmp_path / "sft").mkdir()
    manifest = build_manifest(tmp_path / "sft", "sft")
    assert manifest["status"] == "DRAFT"
    assert manifest["sample_count"] == 0
    assert manifest["hash"] is None
    assert manifest["source_types"] == []


def test_baseline_is_explicitly_not_run_without_real_evaluator():
    report = run_baseline(model=None, dataset_version=None)
    assert report["experiment_id"] == "EXP-BASELINE-001"
    assert report["status"] == "NOT RUN"
    assert all(value is None for value in report["metrics"].values())
