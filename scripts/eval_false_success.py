"""Evaluate frozen synthetic cases. Labels never enter the inspector context.

v3 (SCORE-P0-01): 明确二分类与 uncertain 的关系；每个比率给分子/分母；
零分母为 null；silent_pass_fn 加 caveat；执行闸/人工队列在无证据时为 NOT_RUN，
有平台证据时由 silent_release_violation 识别“uncertain 但 UI 显示已恢复/执行仍放行”；
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
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
from agent.inspector.pipeline import InspectorPipeline
from agent.inspector.models import EvidenceItem

FIXTURE = REPO_ROOT / 'tests/fixtures/defense/false_success.json'
DEFAULT_OUTPUT = REPO_ROOT / '06-工程整改/eval_false_success.csv'
SCHEMA_VERSION = 3
PLATFORM_EVIDENCE_FIELDS = (
    'ui_state',
    'execution_permitted',
    'review_task_created',
    'review_task_status',
)
UI_RECOVERED_STATES = frozenset({'RECOVERED', 'VERIFIED', 'SUCCESS', 'ACTIVE', '已恢复'})


# DATA-P0-01: per-case 治理字段的向后兼容默认值。v1 fixture 没有这些字段时自动补。
_PER_CASE_DEFAULTS = {
    "label_source": "unknown",
    "license": None,
    "pii": None,
    "review_status": "unreviewed",
    "evidence_hash": None,
    "duplicate_of": None,
}


def load_cases(path=FIXTURE):
    """读取 fixture 的 cases 列表，兼容 v1/v2 schema。返回 list[case]。"""
    cases, _fixture, _ver = load_fixture(path)
    return cases


def load_fixture(path=FIXTURE):
    """读取整个 fixture dict。自动把 v1 schema 的 case 补成包含治理字段的 v2 形态。

    返回 (cases: list, fixture_dict: dict, fixture_schema_version: int)。
    """
    fixture_path = Path(path)
    fixture = json.loads(fixture_path.read_text(encoding='utf-8'))
    schema_ver = fixture.get('schema_version', 1)
    raw_cases = fixture['cases']
    normalized = []
    for c in raw_cases:
        new = dict(c)
        for k, v in _PER_CASE_DEFAULTS.items():
            new.setdefault(k, v)
        normalized.append(new)
    return normalized, fixture, schema_ver


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


def attach_platform_evidence(rows, evidence):
    """把平台侧证据（UI 状态/执行许可/复核任务）逐行挂到结果上。

    证据缺省时字段为 None，后续汇总据此返回 NOT_RUN，不默认记 0 或 100%。
    """
    normalized: dict[str, dict[str, Any]] = {}
    for sample_id, item in (evidence or {}).items():
        if not isinstance(sample_id, str) or not isinstance(item, Mapping):
            raise ValueError('platform_evidence 必须是 {sample_id: object}')
        unknown = set(item) - set(PLATFORM_EVIDENCE_FIELDS)
        if unknown:
            raise ValueError(f'platform_evidence[{sample_id}] 含未知字段：{sorted(unknown)}')
        normalized[sample_id] = dict(item)

    merged_rows = []
    for row in rows:
        merged = dict(row)
        recorded = normalized.get(row['sample_id'], {})
        for field in PLATFORM_EVIDENCE_FIELDS:
            merged[field] = recorded.get(field)
        merged_rows.append(merged)
    return merged_rows


def _ui_shows_recovered(value) -> bool:
    return isinstance(value, str) and value.strip().upper() in UI_RECOVERED_STATES


def summarize_execution_gate(rows):
    """执行闸指标：无平台证据即 NOT_RUN；有证据时单列错放与静默放行反例。"""
    recorded = [
        row for row in rows
        if row.get('execution_permitted') is not None or row.get('ui_state') is not None
    ]
    if not recorded:
        return {
            "status": "NOT_RUN",
            "evidence_rows": 0,
            "false_release_n": "NOT_RUN",
            "false_release_rate": "NOT_RUN",
            "silent_release_violation_n": "NOT_RUN",
            "silent_release_violation_rate": "NOT_RUN",
            "violation_sample_ids": [],
            "definition": (
                "未采集 UI/执行闸证据，故不放行指标为 NOT_RUN。"
                "不得把结论降级为 0 或 100%。"
            ),
        }

    positives = [row for row in recorded if row['expected_false_success'] is True]
    uncertain_rows = [row for row in recorded if row['uncertain']]
    false_release = [
        row for row in positives
        if row.get('execution_permitted') is True and not row['detected_false_success']
    ]
    # 反例识别：Inspector 已给 uncertain（未确认恢复）却仍显示已恢复或放行执行。
    violations = [
        row for row in uncertain_rows
        if row.get('execution_permitted') is True or _ui_shows_recovered(row.get('ui_state'))
    ]
    return {
        "status": "RAN",
        "evidence_rows": len(recorded),
        "false_release_n": len(false_release),
        "false_release_rate": _ratio(len(false_release), len(positives)),
        "silent_release_violation_n": len(violations),
        "silent_release_violation_rate": _ratio(len(violations), len(uncertain_rows)),
        "violation_sample_ids": [row['sample_id'] for row in violations],
        "definition": (
            "false_release = expected=True ∧ execution_permitted=True ∧ 未检出；"
            "silent_release_violation = uncertain=True ∧ (UI 显示已恢复 ∨ execution_permitted=True)。"
            "两个比率分母分别为“有证据的正例数”和“有证据的 uncertain 数”，零分母为 null。"
        ),
    }


def summarize_review_queue(rows):
    """复核队列指标：区分“标记需复核”与“任务已创建/已送达”。"""
    needed = [row for row in rows if row['uncertain']]
    recorded = [row for row in rows if row.get('review_task_created') is not None]
    if not recorded:
        return {
            "review_needed_n": len(needed),
            "review_task_created_n": "NOT_RUN",
            "review_task_created": "NOT_RUN",
            "review_task_status": "NOT_RUN",
            "note": "无人工队列证据：只统计 uncertain=True 的“需复核数”，创建/送达记 NOT_RUN。",
        }

    created = [row for row in recorded if row.get('review_task_created') is True]
    statuses: dict[str, int] = {}
    for row in created:
        key = row.get('review_task_status') or 'UNKNOWN'
        statuses[key] = statuses.get(key, 0) + 1
    return {
        "review_needed_n": len(needed),
        "review_task_created_n": len(created),
        "review_task_created": len(created),
        "review_task_created_rate": _ratio(len(created), len(needed)),
        "review_task_status": statuses,
        "note": "review_task_created 仅统计确已创建任务的行；状态按任务状态计数。",
    }


def evaluate(cases=None, platform_evidence=None, fixture=None):
    """评分入口。

    - cases=None：从默认 fixture 读取。同时返回 fixture dict 用于 data_governance。
    - 显式传 cases：fixture 必须也显式传（或传 None 表示未知 provenance）。
    """
    if cases is None:
        cases, fixture, _fixture_ver = load_fixture()
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
            # DATA-P0-01 治理元数据（v2 fixture 有值，v1 fixture 默认值）
            'label_source': case.get('label_source', _PER_CASE_DEFAULTS['label_source']),
            'review_status': case.get('review_status', _PER_CASE_DEFAULTS['review_status']),
            'license': case.get('license'),
            'pii': case.get('pii'),
            'evidence_hash': case.get('evidence_hash'),
            'duplicate_of': case.get('duplicate_of'),
        })

    rows = attach_platform_evidence(rows, platform_evidence)

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

    # DATA-P0-01 分组统计
    per_source = {}
    for src in sorted(set(r['label_source'] for r in rows)):
        sub = [r for r in scored if r['label_source'] == src]
        if not sub:
            per_source[src] = {"scored_n": 0, "note": "no scored rows in this source"}
            continue
        s_tp = sum(1 for r in sub if r['expected_false_success'] is True and r['detected_false_success'])
        s_tn = sum(1 for r in sub if r['expected_false_success'] is False and not r['detected_false_success'])
        s_fp = sum(1 for r in sub if r['expected_false_success'] is False and r['detected_false_success'])
        s_fn = sum(1 for r in sub if r['expected_false_success'] is True and not r['detected_false_success'])
        s_prec = _ratio(s_tp, s_tp + s_fp)
        s_rec = _ratio(s_tp, s_tp + s_fn)
        if s_prec['value'] is None or s_rec['value'] is None or s_prec['value'] + s_rec['value'] == 0:
            s_f1 = None
        else:
            s_f1 = 2 * s_prec['value'] * s_rec['value'] / (s_prec['value'] + s_rec['value'])
        per_source[src] = {
            "scored_n": len(sub),
            "positive_n": sum(1 for r in sub if r['expected_false_success'] is True),
            "negative_n": sum(1 for r in sub if r['expected_false_success'] is False),
            "TP": s_tp, "TN": s_tn, "FP": s_fp, "FN": s_fn,
            "precision": s_prec, "recall": s_rec,
            "F1": s_f1,
        }

    per_review = {}
    for st in sorted(set(r['review_status'] for r in rows)):
        sub_all = [r for r in rows if r['review_status'] == st]
        sub_scored = [r for r in scored if r['review_status'] == st]
        per_review[st] = {
            "case_n": len(sub_all),
            "scored_n": len(sub_scored),
            "positive_n": sum(1 for r in sub_scored if r['expected_false_success'] is True),
            "negative_n": sum(1 for r in sub_scored if r['expected_false_success'] is False),
        }

    fixture_prov = None
    fixture_schema_ver = None
    fixture_case_n = len(rows)
    if fixture is not None:
        fixture_schema_ver = fixture.get('schema_version', 1)
        raw_prov = fixture.get('provenance')
        if isinstance(raw_prov, str):
            fixture_prov = {"legacy_text": raw_prov}
        else:
            fixture_prov = raw_prov

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
        "review_queue": summarize_review_queue(rows),
        "execution_gate": summarize_execution_gate(rows),
        # DATA-P0-01 数据治理元数据
        "data_governance": {
            "fixture_schema_version": fixture_schema_ver,
            "fixture_provenance": fixture_prov,
            "fixture_case_n": fixture_case_n,
            "per_label_source": per_source,
            "per_review_status": per_review,
            "note": (
                "per_label_source 的 TP/TN/FP/FN 仅统计 scored rows "
                "(expected_false_success is not None)；label_source=unknown 表示 fixture 未声明来源。"
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
    parser.add_argument('--platform-evidence', type=Path, default=None,
                        help='可选：{sample_id: {ui_state, execution_permitted, review_task_created, review_task_status}} JSON')
    args = parser.parse_args()

    fixture = Path(args.fixture)
    fixture_bytes = fixture.read_bytes()
    fixture_sha = hashlib.sha256(fixture_bytes).hexdigest()

    script_path = Path(__file__)
    script_sha = hashlib.sha256(script_path.read_bytes()).hexdigest()

    platform_evidence = None
    if args.platform_evidence is not None:
        platform_evidence = json.loads(args.platform_evidence.read_text(encoding='utf-8'))
        metrics_evidence = {
            'path': str(args.platform_evidence),
            'sha256': hashlib.sha256(args.platform_evidence.read_bytes()).hexdigest(),
        }
    else:
        metrics_evidence = {'path': None, 'sha256': None}

    cases, fixture_dict, _fixture_ver = load_fixture(fixture)
    rows, metrics = evaluate(cases, platform_evidence=platform_evidence, fixture=fixture_dict)
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
    metrics['platform_evidence'] = metrics_evidence

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
    gate = metrics['execution_gate']
    print(f"execution_gate.status={gate['status']}  false_release_n={gate['false_release_n']}  "
          f"silent_release_violation_n={gate['silent_release_violation_n']}")
    queue = metrics['review_queue']
    print(f"review_needed_n={queue['review_needed_n']}  review_task_created={queue['review_task_created']}")
    print(f"CSV: {args.output}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
