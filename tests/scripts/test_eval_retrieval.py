from scripts.eval_retrieval import build_variants, compute_metrics, extract_samples


def test_extracts_fourteen_samples_and_five_variants_per_sample():
    samples = extract_samples("SmartOps-Dataset/Linux")
    assert len(samples) == 14
    assert all(len(build_variants(sample)) == 5 for sample in samples)


def test_synthetic_rewrites_do_not_claim_human_provenance():
    samples = extract_samples("SmartOps-Dataset/Linux")
    variants = [variant for sample in samples for variant in build_variants(sample)]
    generated = [query for query, provenance in variants if provenance.startswith("generated:")]
    human = [query for query, provenance in variants if provenance.startswith("human:")]

    assert len(variants) == 70
    assert len(human) == 0
    assert len(generated) == 56
    assert all(provenance.startswith(("dataset:", "generated:"))
               for sample in samples for _, provenance in build_variants(sample))


def test_each_sample_has_three_distinct_scenario_rewrites():
    samples = extract_samples("SmartOps-Dataset/Linux")
    for sample in samples:
        variants = build_variants(sample)
        scenario_queries = [query for query, provenance in variants if provenance.startswith("generated:scenario")]
        assert len(scenario_queries) == 3
        assert len(set(scenario_queries)) == len(scenario_queries)


def test_compute_metrics_uses_top_three_and_reciprocal_rank():
    metrics = compute_metrics(
        [["wrong", "target"], ["wrong"], ["target"]],
        ["target", "target", "target"],
    )
    assert metrics["recall_at_3"] == 2 / 3
    assert metrics["mrr"] == (0.5 + 0.0 + 1.0) / 3
