from copy import deepcopy
from scripts import eval_false_success as evaluator
from agent.inspector.pipeline import InspectorPipeline


def test_frozen_cases_have_six_categories_and_ten_distractors():
    cases = evaluator.load_cases()
    assert len(cases) == 50
    assert sum(case['category'] == 'distractor' for case in cases) == 10
    assert len({case['category'] for case in cases}) == 7
    assert all('resolved' not in case for case in cases)


def test_changing_expected_label_never_changes_prediction():
    pipeline = InspectorPipeline()
    case = evaluator.load_cases()[0]
    other = deepcopy(case)
    other['expected_false_success'] = not case['expected_false_success']
    assert evaluator.predict(case, pipeline).verification_result == evaluator.predict(other, pipeline).verification_result


def test_unknown_observations_are_excluded_from_binary_denominator():
    rows, metrics = evaluator.evaluate()
    sizes = metrics['input_sizes']
    assert sizes['total_rows'] == len(rows) == 50
    assert sizes['scored_n'] + sizes['unscored_n'] == 50
    assert sizes['unscored_n'] == 3
    bc = metrics['binary_classification']
    assert bc['TP'] + bc['TN'] + bc['FP'] + bc['FN'] == sizes['scored_n']
    assert all(row['unverifiable'] for row in rows if row['expected_false_success'] is None)


def test_schema_version_and_ratios_have_num_den_value():
    _, metrics = evaluator.evaluate()
    assert metrics['schema_version'] == 2
    bc = metrics['binary_classification']
    for key in ('precision', 'recall', 'F1'):
        r = bc[key]
        assert 'num' in r and 'den' in r and 'value' in r


def test_zero_denominator_ratio_is_null_not_zero():
    # Synthetic: build a scenario where tp+fp=0 → precision denominator = 0
    # We can't easily manufacture this via pipeline, but _ratio helper is the contract
    assert evaluator._ratio(0, 0) == {"num": 0, "den": 0, "value": None}
    assert evaluator._ratio(5, 0) == {"num": 5, "den": 0, "value": None}
    assert evaluator._ratio(5, 10) == {"num": 5, "den": 10, "value": 0.5}


def test_holdout_uncertain_positives_count_as_fn():
    """Taskbook §3.1: 10 uncertain positive cases must enter FN, NOT excluded from F1 denominator."""
    holdout_path = evaluator.REPO_ROOT / 'tests/fixtures/defense/false_success_holdout.json'
    rows, metrics = evaluator.evaluate(evaluator.load_cases(holdout_path))
    bc = metrics['binary_classification']
    ub = metrics['uncertain_breakdown']
    # Holdout: TP=5, TN=4, FP=1, FN=10, F1≈0.4762
    assert bc['TP'] == 5
    assert bc['TN'] == 4
    assert bc['FP'] == 1
    assert bc['FN'] == 10
    # 10 uncertain positive → FN must include these
    assert ub['uncertain_positive'] == 10
    # FN >= uncertain_positive (all uncertain positives are in FN because expected=True, detected=False)
    assert bc['FN'] >= ub['uncertain_positive']
    # F1 matches expected 0.4762-ish
    assert abs(bc['F1']['value'] - 0.47619047619047616) < 1e-9


def test_execution_gate_and_review_queue_are_not_run_without_evidence():
    _, metrics = evaluator.evaluate()
    assert metrics['execution_gate']['false_release_n'] == 'NOT_RUN'
    assert metrics['review_queue']['review_task_created'] == 'NOT_RUN'
    assert metrics['review_queue']['review_task_status'] == 'NOT_RUN'


def test_false_verification_is_distinct_from_legacy_silent_pass_fn_concept():
    """false_verified_n = cases that are expected=True, NOT detected, AND NOT uncertain.
    These are the truly 'slipped through as verified OK' cases.
    """
    rows, metrics = evaluator.evaluate()
    fv = metrics['false_verification']
    # Both are present
    assert 'false_verified_n' in fv
    assert 'legacy_silent_pass_fn' in fv
    # They are the same number (definition preserved) but the NEW name is explicit
    assert fv['false_verified_n'] == fv['legacy_silent_pass_fn']
