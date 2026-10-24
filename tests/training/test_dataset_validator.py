import json

from training.dataset_validator import validate_dataset
from training.evaluation_runner import not_run_report


def test_sft_validation_detects_duplicate_and_empty_field(tmp_path):
    sample = {"instruction": "诊断 Nginx 502", "input": {"evidence": ["502"]}, "output": {"risk": "LOW"}}
    (tmp_path / "samples.json").write_text(json.dumps([sample, sample, {"instruction": "", "input": {}, "output": {}}]), encoding="utf-8")
    report = validate_dataset(tmp_path, "sft")
    assert report.samples == 3
    assert report.valid == 1
    assert report.duplicates == 1
    assert report.invalid == 2


def test_evidence_validation_rejects_invalid_label(tmp_path):
    (tmp_path / "evidence.jsonl").write_text(json.dumps({"claim": "x", "evidence": ["y"], "label": "MADE_UP"}), encoding="utf-8")
    report = validate_dataset(tmp_path, "evidence")
    assert report.invalid == 1


def test_evaluation_report_contains_no_fake_values():
    report = not_run_report()
    assert report["status"] == "NOT RUN"
    assert all(value is None for value in report["metrics"].values())
