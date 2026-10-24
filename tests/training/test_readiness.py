from training.readiness.dataset_check import check_datasets
from training.readiness.report import build_report


def test_empty_manifests_block_training(tmp_path):
    dataset_root = tmp_path / "data" / "training"
    (dataset_root / "sft").mkdir(parents=True)
    (dataset_root / "sft" / "manifest.json").write_text(
        '{"dataset_id":"smartops-sft","version":"v0.1","status":"DRAFT","sample_count":0,"approved_count":0}',
        encoding="utf-8",
    )
    result = check_datasets(dataset_root)
    assert result["status"] == "BLOCKED"
    assert result["ready_count"] == 0


def test_report_blocks_sft_without_dataset_or_model():
    report = build_report({
        "requirements": {"status": "PARTIAL", "reason": "missing"},
        "model": {"status": "BLOCKED", "reason": "missing"},
        "dataset": {"status": "BLOCKED", "reason": "missing"},
        "hardware": {"status": "READY", "reason": "available"},
    })
    assert report["status"] == "BLOCKED"
    assert report["gates"]["sft"] == "BLOCKED"
    assert report["training_started"] is False
    assert report["secrets_included"] is False
