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
    assert metrics['schema_version'] == 3
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
    assert metrics['execution_gate']['silent_release_violation_n'] == 'NOT_RUN'
    assert metrics['review_queue']['review_task_created'] == 'NOT_RUN'
    assert metrics['review_queue']['review_task_status'] == 'NOT_RUN'


# ---------------------------------------------------------------------------
# 验收反例：uncertain=true 但 UI 显示已恢复 / 执行仍放行，必须被新指标识别
# ---------------------------------------------------------------------------

def _row(sample_id, expected, detected, uncertain, **extra):
    row = {
        'sample_id': sample_id,
        'expected_false_success': expected,
        'detected_false_success': detected,
        'uncertain': uncertain,
    }
    row.update(extra)
    return row


def test_uncertain_but_ui_recovered_and_released_is_flagged():
    rows = evaluator.attach_platform_evidence(
        [
            _row('s1', expected=True, detected=False, uncertain=True),
            _row('s2', expected=True, detected=False, uncertain=True),
            _row('s3', expected=False, detected=False, uncertain=False),
        ],
        {
            's1': {'ui_state': 'RECOVERED', 'execution_permitted': True},
            's2': {'ui_state': 'NEEDS_REVIEW', 'execution_permitted': False},
            's3': {'ui_state': 'OK', 'execution_permitted': True},
        },
    )
    gate = evaluator.summarize_execution_gate(rows)
    assert gate['status'] == 'RAN'
    assert gate['silent_release_violation_n'] == 1
    assert gate['violation_sample_ids'] == ['s1']
    assert gate['silent_release_violation_rate'] == {'num': 1, 'den': 2, 'value': 0.5}
    # s1 未检出却放行，同时计入错放
    assert gate['false_release_n'] == 1
    assert gate['false_release_rate'] == {'num': 1, 'den': 2, 'value': 0.5}


def test_ui_recovered_without_release_still_counts_as_silent_release_candidate():
    rows = evaluator.attach_platform_evidence(
        [_row('s1', expected=True, detected=False, uncertain=True)],
        {'s1': {'ui_state': '已恢复'}},
    )
    gate = evaluator.summarize_execution_gate(rows)
    assert gate['silent_release_violation_n'] == 1
    assert gate['violation_sample_ids'] == ['s1']
    # 未提供 execution_permitted：错放指标的分母仍为 1，但放行数按布尔精确计数
    assert gate['false_release_n'] == 0


def test_review_queue_distinguishes_needed_from_created():
    rows = evaluator.attach_platform_evidence(
        [
            _row('s1', expected=True, detected=False, uncertain=True),
            _row('s2', expected=True, detected=False, uncertain=True),
            _row('s3', expected=False, detected=False, uncertain=False),
        ],
        {
            's1': {'review_task_created': True, 'review_task_status': 'OPEN'},
            's2': {'review_task_created': False},
            's3': {'review_task_created': False},
        },
    )
    queue = evaluator.summarize_review_queue(rows)
    assert queue['review_needed_n'] == 2
    assert queue['review_task_created_n'] == 1
    assert queue['review_task_created_rate'] == {'num': 1, 'den': 2, 'value': 0.5}
    assert queue['review_task_status'] == {'OPEN': 1}


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


# ================================================================
# DATA-P0-01 fixtures：schema v2 兼容 + 分组统计
# ================================================================


def test_v1_fixture_auto_upgrades_to_v2_defaults(tmp_path):
    """DATA-P0-01：v1 fixture（无治理字段，provenance 是 string）读入后自动补默认治理值。

    关键：label 本身不变，所以 BC 数值应该和 v2 fixture 完全一致。
    """
    import json
    import pathlib

    # 把当前 v2 fixture 降回 v1 形态
    fixture_v2_path = pathlib.Path(evaluator.FIXTURE)
    v2 = json.loads(fixture_v2_path.read_text(encoding='utf-8'))
    v1_cases = []
    for c in v2['cases']:
        v1_case = {k: c[k] for k in ('id', 'category', 'claim', 'probes',
                                     'expected_false_success', 'label_reason')}
        v1_cases.append(v1_case)
    v1 = {"schema_version": 1, "provenance": "legacy text provenance",
          "limitations": v2.get('limitations', ''), "cases": v1_cases}

    # 写临时 v1 fixture，用 load_fixture 读入
    tmp_path.joinpath('v1_test.json').write_text(
        json.dumps(v1, ensure_ascii=False), encoding='utf-8')
    cases_auto, fixture_dict, schema_ver = evaluator.load_fixture(
        tmp_path / 'v1_test.json')

    assert schema_ver == 1
    # 每个 case 应该被补治理字段
    assert all(c.get('label_source') == 'unknown' for c in cases_auto)
    assert all(c.get('review_status') == 'unreviewed' for c in cases_auto)
    assert fixture_dict.get('provenance') == 'legacy text provenance'

    # 跑 evaluate，BC 数值应和默认 v2 fixture 一致（因为 label 没变）
    rows_v1, metrics_v1 = evaluator.evaluate(cases_auto, fixture=fixture_dict)
    rows_v2, metrics_v2 = evaluator.evaluate()

    bc1 = metrics_v1['binary_classification']
    bc2 = metrics_v2['binary_classification']
    assert bc1['TP'] == bc2['TP']
    assert bc1['TN'] == bc2['TN']
    assert bc1['FP'] == bc2['FP']
    assert bc1['FN'] == bc2['FN']
    assert bc1['F1']['value'] == bc2['F1']['value']

    # data_governance 节存在，fixture_schema_version 应是 1（v1 升级）
    dg = metrics_v1['data_governance']
    assert dg['fixture_schema_version'] == 1
    # provenance 是字符串 → 被包装成 {"legacy_text": ...}
    assert dg['fixture_provenance'] == {"legacy_text": "legacy text provenance"}


def test_data_governance_groups_by_label_source_and_review_status():
    """DATA-P0-01：当前 v2 fixture 全部 synthetic_dev / unreviewed，分组统计应覆盖到 BC 数值。"""
    rows, metrics = evaluator.evaluate()
    dg = metrics['data_governance']
    bc = metrics['binary_classification']

    assert dg['fixture_schema_version'] == 2
    assert dg['fixture_case_n'] == len(rows)

    # per_label_source 分组：只有 synthetic_dev，覆盖 BC 数值
    assert 'synthetic_dev' in dg['per_label_source']
    src = dg['per_label_source']['synthetic_dev']
    assert src['TP'] == bc['TP']
    assert src['TN'] == bc['TN']
    assert src['FP'] == bc['FP']
    assert src['FN'] == bc['FN']
    assert src['scored_n'] == bc['TP'] + bc['TN'] + bc['FP'] + bc['FN']
    assert src['F1'] is not None  # synthetic_dev 有正有负，F1 应可计算

    # per_review_status 分组：只有 unreviewed
    assert dg['per_review_status'] == {'unreviewed': {
        'case_n': dg['fixture_case_n'],
        'scored_n': src['scored_n'],
        'positive_n': src['positive_n'],
        'negative_n': src['negative_n'],
    }}
