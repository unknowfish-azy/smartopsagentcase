from training.dataset_builders import to_evidence, to_inspector, to_preference, to_sft
from training.synthetic_incidents import generate_incident


def test_builders_preserve_provenance_and_pending_quality():
    record = generate_incident(1).to_dict()
    for builder, dataset_type in (
        (to_sft, "SFT"), (to_preference, "PREFERENCE"),
        (to_evidence, "EVIDENCE"), (to_inspector, "INSPECTOR"),
    ):
        result = builder(record)
        assert result["dataset_type"] == dataset_type
        assert result["source"]["data_class"] == "SYNTHETIC"
        assert result["quality"]["status"] == "PENDING"
        assert result["metadata"]["scenario_id"] == record["metadata"]["scenario_id"]


def test_preference_has_distinct_chosen_and_rejected_behavior():
    result = to_preference(generate_incident(3).to_dict())
    preference = result["expected_behavior"]
    assert preference["chosen"] != preference["rejected"]
    assert "EVIDENCE_FIRST" in preference["principles"]


def test_difficult_evidence_and_inspector_candidates_are_uncertain():
    record = generate_incident(2, difficult=True).to_dict()
    evidence = to_evidence(record)
    inspector = to_inspector(record)
    assert evidence["output"]["label"] == "PARTIALLY_SUPPORTED"
    assert inspector["output"]["requires_human"] is True
    assert inspector["output"]["decision"] == "WARNING"
