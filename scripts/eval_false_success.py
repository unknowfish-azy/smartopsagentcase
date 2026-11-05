"""Evaluate frozen synthetic cases. Labels never enter the inspector context.

v2 (SCORE-P0-01): 明确二分类与 uncertain 的关系；每个比率给分子/分母；
零分母为 null；silent_pass_fn 加 caveat；执行闸/人工队列为 NOT_RUN；
fixture 与脚本哈希、schema_version 绑定同一输入版本。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from agent.inspector.pipeline import InspectorPipeline
from agent.inspector.models import EvidenceItem

FIXTURE = REPO_ROOT / 'tests/fixtures/defense/false_success.json'
DEFAULT_OUTPUT = REPO_ROOT / '06-工程整改/eval_false_success.csv'
SCHEMA_VERSION = 2


def load_cases(path=FIXTURE):
    return json.loads(Path(path).read_text(encoding='utf-8'))['cases']


def predict(case, pipeline):
    # Only facts and the claim enter prediction. Labels remain outside.
    probes = case['probes']
    return pipeline.run({
        'task_id': case['id'], 'target': 'SERVICE', 'agent_claim': case['claim'],
        'actual_state': {'probes': probes},
        'evidence': [EvidenceItem(content=json.dumps(probes, ensure_ascii=False), source='synthetic fixture')],
    })


def _ratio(num, den):
    """Return {'num': n, 'den': d, 'value': float_or_None}. Zero denominator → value=None."""
    if den == 0:
        return {"num": num, "den": den, "value": None}
    return {"num": num, "den": den, "value": num / den}


def evaluate(cases=None):
    cases = load_cases() if cases is None else cases
    pipeline = InspectorPipeline()
    rows = []
    for case in cases:
        result = predict(case, pipeline)
        verification = result.verification_result or {}
        unknown = verification.get('checked') is not True
        detected = bool(verification.get('false_success'))
        uncertain = bool(verification.get('uncertain'))
        rows.append({
            'sample_id': case['id'],
            'category': case['category'],
            'claim': case['claim'],
            'probe_shape': json.dumps(case['probes'], ensure_ascii=False),
            'expected_false_success': case['expected_false_success'],
            'detected_false_success': detected,
            'unverifiable': unknown,
            'uncertain': uncertain,
            'claim_state': verification.get('claim_state'),
            'inspection_status': result.status.value,
            'reason': verification.get('reason'),
            'label_reason': case['label_reason'],
        })

    scored = [r for r in rows if r['expected_false_success'] is not None]
    unscored = [r for r in rows if r['expected_false_success'] is None]

    tp = sum(1 for r in scored if r['expected_false_success'] is True and r['detected_false_success'])
    tn = sum(1 for r in scored if r['expected_false_success'] is False and not r['detected_false_success'])
    fp = sum(1 for r in scored if r['expected_false_success'] is False and r['detected_false_success'])
    fn = sum(1 for r in scored if r['expected_false_success'] is True and not r['detected_false_success'])

    pos_n = sum(1 for r in scored if r['expected_false_success'] is True)
    neg_n = sum(1 for r in scored if r['expected_false_success'] is False)

    # uncertain breakdown
    uncertain_pos = sum(1 for r in scored if r['expected_false_success'] is True and r['uncertain'])
    uncertain_neg = sum(1 for r in scored if r['expected_false_success'] is False and r['uncertain'])
    uncertain_all = uncertain_pos + uncertain_neg

    # false verification: expected=True but NOT detected AND NOT uncertain
    # These are the cases that Inspector let "slip through" as verified-ok
    false_verified = sum(1 for r in scored
                         if r['expected_false_success'] is True
                         and not r['detected_false_success']
                         and not r['uncertain'])

    # legacy silent_pass_fn — same as false_verified, kept for backward compat
    silent_pass_fn = false_verified

    precision_r = _ratio(tp, tp + fp)
    recall_r = _ratio(tp, tp + fn)
    if precision_r['value'] is None or recall_r['value'] is None:
        f1_value = None
    elif precision_r['value'] + recall_r['value'] == 0:
        f1_value = 0.0
    else:
        f1_value = 2 * precision_r['value'] * recall_r['value'] / (precision_r['value'] + recall_r['value'])

    return rows, {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "binary_classification": {
            "note": (
                "expected_false_success=True and not detected_false_success counts as FN "
                "even when uncertain=True. unscored (expected_false_success=None) excluded from denominator."
            ),
            "TP": tp, "TN": tn, "FP": fp, "FN": fn,
            "positive_n": pos_n, "negative_n": neg_n,
            "precision": precision_r,
            "recall": recall_r,
            "F1": {"num": 2 * (precision_r['value'] or 0) * (recall_r['value'] or 0),
                   "den": (precision_r['value'] or 0) + (recall_r['value'] or 0),
                   "value": f1_value},
        },
        "uncertain_breakdown": {
            "uncertain_total": uncertain_all,
            "uncertain_positive": uncertain_pos,
            "uncertain_negative": uncertain_neg,
            "uncertain_ratio_of_scored": _ratio(uncertain_all, len(scored)),
            # coverage = fraction of scored cases where Inspector gave an explicit (non-uncertain) judgment
            "explicit_coverage": _ratio(len(scored) - uncertain_all, len(scored)),
        },
        "false_verification": {
            # expected=True, not detected, and NOT uncertain → truly "verified OK" when should have flagged
            "false_verified_n": false_verified,
            "false_verified_rate": _ratio(false_verified, pos_n),
            "legacy_silent_pass_fn": silent_pass_fn,
            "definition": (
                "legacy silent_pass_fn = false_verified_n. "
                "NOTE: this only inspects Inspector output fields (verification_result.false_success / uncertain). "
                "It does NOT inspect UI, execution gate state, or human review queue — "
                "a value of 0 here does NOT prove zero real-world silent release."
            ),
        },
        "review_queue": {
            # Cases that need human review = uncertain=True regardless of expected label
            "review_needed_n": uncertain_all,
            "review_needed_positive_n": uncertain_pos,
            "review_needed_negative_n": uncertain_neg,
            "review_task_created": "NOT_RUN",
            "review_task_status": "NOT_RUN",
            "note": "No integration with real task queue; review_needed_n counts uncertain=True rows.",
        },
        "execution_gate": {
            "false_release_n": "NOT_RUN",
            "note": (
                "No E2E/UI/execution-gate evidence collected in SCORE-P0-01. "
                "This metric waits for E2E-OBS-P0-01 to wire real gate inspection."
            ),
        },
        "input_sizes": {
            "total_rows": len(rows),
            "scored_n": len(scored),
            "unscored_n": len(unscored),
        },
        "row_schema": list(rows[0].keys()) if rows else [],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--fixture', type=Path, default=FIXTURE,
                        help='fixture 路径；留出集用 tests/fixtures/defense/false_success_holdout.json')
    parser.add_argument('--metrics-json', type=Path, default=None,
                        help='可选：将完整 metrics dict 写成 JSON（默认只打印）')
    args = parser.parse_args()

    fixture = Path(args.fixture)
    fixture_bytes = fixture.read_bytes()
    fixture_sha = hashlib.sha256(fixture_bytes).hexdigest()

    script_path = Path(__file__)
    script_sha = hashlib.sha256(script_path.read_bytes()).hexdigest()

    rows, metrics = evaluate(load_cases(fixture))
    def _rel(p):
        try:
            return str(Path(p).resolve().relative_to(REPO_ROOT))
        except ValueError:
            return str(p)
    metrics['fixture'] = {
        'path': _rel(fixture),
        'sha256': fixture_sha,
    }
    metrics['script'] = {
        'path': _rel(script_path),
        'sha256': script_sha,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    if args.metrics_json:
        args.metrics_json.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"metrics_json: {args.metrics_json}")

    # concise summary for quick scan
    bc = metrics['binary_classification']
    ub = metrics['uncertain_breakdown']
    print("---")
    print(f"schema_version={metrics['schema_version']}  fixture_sha256={fixture_sha[:16]}…  script_sha256={script_sha[:16]}…")
    print(f"scored={bc['TP']+bc['TN']+bc['FP']+bc['FN']}  TP={bc['TP']} TN={bc['TN']} FP={bc['FP']} FN={bc['FN']}")
    f1v = bc['F1']['value']
    print(f"precision={bc['precision']['value']}  recall={bc['recall']['value']}  F1={f1v}")
    print(f"uncertain_total={ub['uncertain_total']}  uncertain_pos={ub['uncertain_positive']}  uncertain_neg={ub['uncertain_negative']}")
    print(f"explicit_coverage={ub['explicit_coverage']['value']}  false_verified_n={metrics['false_verification']['false_verified_n']}")
    print(f"FN includes uncertain-positive by design (taskbook §3.1).")
    print(f"execution_gate=false_release_n: NOT_RUN (no E2E/UI evidence yet).")
    print(f"CSV: {args.output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
