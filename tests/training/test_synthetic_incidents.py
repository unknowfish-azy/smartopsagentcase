from training.synthetic_incidents import INCIDENT_DEFINITIONS, generate_catalog, generate_incident


def test_catalog_covers_ten_incident_families_and_marks_synthetic():
    catalog = generate_catalog()
    assert len(catalog) == 10
    assert len({item["metadata"]["incident_family"] for item in catalog}) == 10
    assert all(item["source"]["data_class"] == "SYNTHETIC" for item in catalog)
    assert all(item["source"]["source_type"] == "SYNTHETIC_INCIDENT" for item in catalog)


def test_difficult_cases_have_conflict_and_uncertainty():
    incident = generate_incident(2, difficult=True).to_dict()
    assert incident["metadata"]["difficulty"] == "HARD"
    assert incident["output"]["diagnosis"] == "UNKNOWN"
    assert incident["verification"]["status"] == "UNKNOWN"
    assert any(item["support_relation"] == "CONTRADICTED" for item in incident["evidence"])


def test_high_risk_network_case_requires_approval():
    incident = generate_incident(10).to_dict()
    assert incident["output"]["risk"] == "HIGH"
    assert incident["output"]["approval_required"] is True
    assert "network.firewall_change" in incident["expected_behavior"]["forbidden_tools"]


def test_generator_bounds_are_explicit():
    assert len(INCIDENT_DEFINITIONS) == 10
    for invalid in (0, 11):
        try:
            generate_incident(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("invalid incident index must be rejected")
