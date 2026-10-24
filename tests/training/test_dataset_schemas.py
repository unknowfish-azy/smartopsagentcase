import json

import pytest

from training.schema_registry import load_catalog, load_schema, schema_path, schema_version


def test_catalog_references_existing_json_schemas():
    catalog = load_catalog()
    assert catalog["status"] == "ACTIVE"
    assert catalog["schema_version"] == "1.0.0"
    for name in catalog["schemas"]:
        path = schema_path(name)
        assert path.is_file()
        assert json.loads(path.read_text(encoding="utf-8"))["$schema"].endswith("2020-12/schema")


def test_unified_sample_schema_has_traceable_envelope():
    schema = load_schema("training_sample")
    required = set(schema["required"])
    assert {
        "sample_id", "dataset_id", "dataset_version", "schema_version",
        "task_type", "environment", "knowledge", "evidence", "policy",
        "expected_behavior", "output", "verification", "inspector",
        "source", "quality", "metadata",
    } <= required
    assert schema["properties"]["schema_version"]["const"] == schema_version()


def test_schema_defines_safety_and_audit_enums():
    schema = load_schema("training_sample")
    definitions = schema["$defs"]
    assert definitions["risk"]["enum"] == ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert "FALSE_SUCCESS" in definitions["verificationOutput"]["properties"]["status"]["enum"]
    assert "APPROVAL" in definitions["inspectorOutput"]["properties"]["category"]["enum"]
    assert definitions["source"]["properties"]["data_class"]["enum"] == ["REAL", "SYNTHETIC", "DEMO"]


def test_dataset_manifest_requires_version_hash_and_grouped_splits():
    schema = load_schema("dataset_manifest")
    required = set(schema["required"])
    assert {"dataset_id", "version", "schema_version", "sample_count", "hash", "splits"} <= required
    strategies = schema["properties"]["splits"]["properties"]["strategy"]["enum"]
    assert "GROUPED_BY_SCENARIO" in strategies
    assert "RANDOM" not in strategies


def test_unknown_schema_is_rejected():
    with pytest.raises(KeyError):
        load_schema("../../outside")
