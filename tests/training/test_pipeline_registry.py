import pytest

from training.ablation import not_run_plan
from training.model_registry import mark_trained, planned_model
from training.training_pipeline import TrainingConfig, dry_run


def test_training_dry_run_has_no_fake_loss_or_artifact():
    result = dry_run(TrainingConfig("SFT", "base-model", "smartops-sft-v0.1", 1e-4, 1, 1, 1, 1024))
    assert result["status"] == "NOT RUN"
    assert result["loss"] is None
    assert result["artifact"] is None


def test_training_config_rejects_unknown_hardware():
    with pytest.raises(ValueError):
        dry_run(TrainingConfig("SFT", "base", "data", 1e-4, 1, 1, 1, 1024, "TPU"))


def test_registry_cannot_mark_model_trained_without_evidence():
    record = planned_model(model_version="smartops-model-v0.1", base_model="base", dataset_version="v0.1", training_config={})
    assert record["status"] == "PLANNED"
    with pytest.raises(ValueError):
        mark_trained(record, artifact="", evaluation={"status": "NOT RUN"})


def test_ablation_plan_is_not_run_and_has_no_metrics():
    plan = not_run_plan()
    assert plan["status"] == "NOT RUN"
    assert all(item["metrics"] is None for item in plan["rag"] + plan["inspector"])
