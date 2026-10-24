import json

from training.dataset_validator import validate_dataset


def sample(**overrides):
    value = {
        "sample_id": "sample-001",
        "dataset_id": "smartops-sft",
        "dataset_version": "v0.1",
        "schema_version": "1.0.0",
        "dataset_type": "SFT",
        "task_type": "OPS_REASONING",
        "instruction": "分析 Nginx 502",
        "environment": {
            "environment_id": "env-001",
            "observed_at": "2026-09-18T00:00:00Z",
            "os": "Ubuntu 22.04",
        },
        "knowledge": [{
            "knowledge_id": "kb-nginx-124",
            "source": "Nginx Official Guide",
            "version": "1.24",
            "service": "nginx",
            "trust": 0.96,
            "content": "Inspect upstream logs before state changes.",
        }],
        "evidence": [{
            "evidence_id": "ev-001",
            "source": "nginx.error.log",
            "content": "connect() failed (111: Connection refused)",
            "timestamp": "2026-09-18T00:00:00Z",
            "relevance": 0.98,
            "version": "1.24",
            "support_relation": "SUPPORTED",
        }],
        "agent_context": {"available_tools": ["nginx.status", "nginx.logs"]},
        "policy": {"restart_requires_approval": True},
        "expected_behavior": {"principle": "EVIDENCE_FIRST"},
        "output": {
            "diagnosis": "Upstream connection refused",
            "root_cause": "Upstream service unavailable",
            "evidence": ["ev-001"],
            "confidence": 0.9,
            "reasoning_summary": "The error log supports an unavailable upstream.",
            "plan": ["Inspect upstream status"],
            "next_tool": "nginx.status",
            "risk": "LOW",
            "approval_required": False,
            "verification_plan": ["Request the affected URL"],
        },
        "verification": {"status": "NOT_RUN"},
        "inspector": {"status": "PENDING"},
        "source": {
            "source_type": "SYNTHETIC_INCIDENT",
            "source_ref": "scenario/nginx-502/001",
            "created_at": "2026-09-18T00:00:00Z",
            "data_class": "SYNTHETIC",
        },
        "quality": {
            "status": "PENDING",
            "human_review": "NOT_REVIEWED",
            "checks": {},
        },
        "metadata": {
            "incident_family": "nginx-502",
            "root_cause_group": "upstream-unavailable",
            "scenario_id": "nginx-502-001",
        },
    }
    value.update(overrides)
    return value


def write_sample(path, value):
    (path / "samples.jsonl").write_text(
        json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def test_v1_sample_passes_structural_and_semantic_validation(tmp_path):
    write_sample(tmp_path, sample())
    report = validate_dataset(tmp_path, "sft", validation_mode="v1")
    assert report.schema_version == "1.0.0"
    assert report.valid == 1
    assert report.invalid == 0


def test_synthetic_source_cannot_be_labeled_real(tmp_path):
    value = sample()
    value["source"]["data_class"] = "REAL"
    write_sample(tmp_path, value)
    report = validate_dataset(tmp_path, "sft", validation_mode="v1")
    assert report.invalid == 1
    assert "synthetic source must use SYNTHETIC data_class" in report.errors[0]["errors"]


def test_high_risk_without_approval_is_rejected(tmp_path):
    value = sample()
    value["output"]["risk"] = "HIGH"
    value["output"]["approval_required"] = False
    write_sample(tmp_path, value)
    report = validate_dataset(tmp_path, "sft", validation_mode="v1")
    assert report.invalid == 1
    assert "output: HIGH/CRITICAL risk requires approval" in report.errors[0]["errors"]


def test_invalid_trust_and_relevance_are_rejected(tmp_path):
    value = sample()
    value["knowledge"][0]["trust"] = 1.1
    value["evidence"][0]["relevance"] = -0.1
    write_sample(tmp_path, value)
    report = validate_dataset(tmp_path, "sft", validation_mode="v1")
    assert report.invalid == 1
    assert len(report.errors[0]["errors"]) == 2


def test_v1_mode_does_not_promote_legacy_sample(tmp_path):
    write_sample(tmp_path, {"instruction": "x", "input": {"a": 1}, "output": {"b": 1}})
    report = validate_dataset(tmp_path, "sft", validation_mode="v1")
    assert report.valid == 0
    assert report.invalid == 1
