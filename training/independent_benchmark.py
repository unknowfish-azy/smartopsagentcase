"""Hash-verified, independently reviewed evaluation boundary.

No labels or reviewer claims contained in a dataset can approve that dataset.
Expected manifest hash and review receipts are supplied by a trusted host.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit
from typing import Any


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot(path: Path):
    content = path.read_bytes()
    return hashlib.sha256(content).hexdigest(), json.loads(content.decode('utf-8'))


def _probe_valid(probe, row):
    if not isinstance(probe, dict) or not isinstance(probe.get('url'), str):
        return False
    url = urlsplit(probe.get('url', ''))
    status, outcome = probe.get('status'), probe.get('outcome')
    return (url.scheme == 'http' and url.hostname == '127.0.0.1' and bool(url.port)
            and probe.get('mode') == 'CONTROLLED' and isinstance(probe.get('body'), str)
            and probe.get('claim') == row['claim']
            and probe.get('expected_false_success') is row['expected_false_success']
            and ((type(status) is int and 100 <= status <= 599
                  and outcome == ('http_error' if status >= 400 else 'response'))
                 or (status is None and outcome == 'timeout')))



def _contained(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError('invalid artifact path')
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()) or Path(relative).is_absolute():
        raise ValueError('artifact path escape')
    return path


def _normalized(value: Any) -> str:
    return ' '.join(str(value).casefold().split())


def _records(value: Any):
    if isinstance(value, list):
        for row in value:
            yield from _records(row)
    elif isinstance(value, dict):
        yield value
        for field in ('samples', 'records', 'data'):
            if field in value:
                yield from _records(value[field])


def evaluate(manifest_path: str | Path, expected_manifest_sha256: str,
             *, training_paths=(), trusted_reviews=None, predictions=None) -> dict:
    """Fail closed on artifacts/schema/leakage; unreviewed metrics stay None.

    trusted_reviews must be records from the host's human-review control plane,
    never deserialized from the evaluation dataset. Absence is not approval.
    predictions is a host-provided {sample_id: false_success_bool} mapping.
    """
    manifest_path = Path(manifest_path)
    root = manifest_path.parent
    errors: list[str] = []
    samples: list[dict] = []
    training_evidence = []
    try:
        manifest_hash, manifest = _snapshot(manifest_path)
        if not re.fullmatch(r'[0-9a-f]{64}', expected_manifest_sha256 or '') or manifest_hash != expected_manifest_sha256:
            raise ValueError('manifest hash mismatch')
        if not isinstance(manifest, dict):
            raise ValueError('manifest schema: object required')
        if manifest.get('schema_version') != 'independent-v1':
            raise ValueError('manifest schema mismatch')
        sp = _contained(root, manifest['samples_path'])
        samples_hash, samples = _snapshot(sp)
        if samples_hash != manifest['samples_sha256']:
            raise ValueError('samples hash mismatch')
        if not isinstance(samples, list) or not samples:
            raise ValueError('samples must be nonempty array')
        ids = set()
        for row in samples:
            if not isinstance(row, dict):
                raise ValueError('sample schema: object required')
            for field in ('id', 'input', 'incident_family', 'claim'):
                if not isinstance(row.get(field), str) or not row[field].strip():
                    raise ValueError('sample schema: ' + field)
            if row['id'] in ids:
                raise ValueError('duplicate sample id')
            ids.add(row['id'])
            if row.get('split') != 'test' or row.get('origin') not in {'CONTROLLED', 'DEMO', 'INDEPENDENT_OBSERVATION'}:
                raise ValueError('sample schema: split/origin')
            if row.get('derived_from_candidate') is not False:
                raise ValueError('candidate-derived golden rejected')
            if row.get('label_status') != 'pending_review':
                raise ValueError('dataset self-approval rejected')
            if type(row.get('expected_false_success')) is not bool:
                raise ValueError('sample schema: expected_false_success')
            evidence = row['evidence']
            if not isinstance(evidence, dict):
                raise ValueError('evidence schema: object required')
            ep = _contained(root, evidence['path'])
            evidence_hash, probe = _snapshot(ep)
            if evidence_hash != evidence['sha256']:
                raise ValueError('evidence hash mismatch: ' + row['id'])
            # Parse raw observation too; a matching hash of arbitrary text is not evidence.
            if not _probe_valid(probe, row):
                raise ValueError('evidence observation schema invalid')
        train_inputs, train_families = set(), set()
        for item in training_paths:
            path = Path(item)
            content = path.read_bytes()
            file_hash = hashlib.sha256(content).hexdigest()
            payload = json.loads(content.decode('utf-8')) if path.suffix != '.jsonl' else [json.loads(line) for line in content.decode('utf-8').splitlines() if line.strip()]
            # Only actual records or a supported records container qualify.
            if isinstance(payload, list):
                records = payload
            elif isinstance(payload, dict) and any(k in payload for k in ('samples', 'records', 'data')):
                records = next(payload[k] for k in ('samples', 'records', 'data') if k in payload)
            elif isinstance(payload, dict) and any(k in payload for k in ('input', 'instruction', 'question', 'prompt', 'messages')):
                records = [payload]
            else:
                raise ValueError('training schema: no actual records')
            if not isinstance(records, list) or not records:
                raise ValueError('training schema: empty records')
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError('training schema: record must be object')
                inputs = [record[k] for k in ('input', 'instruction', 'question', 'prompt')
                          if isinstance(record.get(k), str) and record[k].strip()]
                if 'messages' in record:
                    messages = record['messages']
                    if not isinstance(messages, list) or any(not isinstance(m, dict) for m in messages):
                        raise ValueError('training schema: invalid messages')
                    inputs += [m['content'] for m in messages if m.get('role') == 'user'
                               and isinstance(m.get('content'), str) and m['content'].strip()]
                metadata = record.get('metadata', {})
                if not isinstance(metadata, dict):
                    raise ValueError('training schema: invalid metadata')
                families = [source[k] for source in (record, metadata)
                            for k in ('incident_family', 'scenario_id', 'incident_type')
                            if isinstance(source.get(k), str) and source[k].strip()]
                if not inputs or not families:
                    raise ValueError('training schema: nonempty input and incident family required')
                train_inputs.update(_normalized(v) for v in inputs)
                train_families.update(_normalized(v) for v in families)
            training_evidence.append({'path': str(path), 'sha256': file_hash, 'record_count': len(records)})
        for row in samples:
            if _normalized(row['input']) in train_inputs or _normalized(row['incident_family']) in train_families:
                errors.append('training/test leakage: ' + row['id'])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(str(exc))
    valid = not errors
    reviews = trusted_reviews or {}
    approved = 0
    for row in samples if valid else []:
        review = reviews.get(row['id'], {})
        if (review.get('decision') == 'approved' and review.get('reviewer_kind') == 'human'
                and isinstance(review.get('reviewer_id'), str) and review['reviewer_id'].strip()
                and review.get('manifest_sha256') == expected_manifest_sha256
                and review.get('evidence_sha256') == row['evidence']['sha256']
                and review.get('expected_false_success') is row['expected_false_success']
                and review.get('reviewed_at')):
            approved += 1
    prediction_valid = (isinstance(predictions, dict) and set(predictions) == {r['id'] for r in samples}
                        and all(type(v) is bool for v in predictions.values())) if valid else False
    ready = valid and approved == len(samples) and bool(training_evidence) and prediction_valid
    score = sum(predictions[r['id']] == r['expected_false_success'] for r in samples) / len(samples) if ready else None
    return {
        'manifest_sha256': expected_manifest_sha256,
        'integrity': {'status': 'PASS' if valid else 'BLOCKED', 'reasons': errors},
        'leakage': {'status': 'BLOCKED' if not valid else 'PASS' if training_evidence else 'NOT_RUN',
                    'training_artifacts': training_evidence},
        'formal': {'status': 'READY' if ready else 'BLOCKED', 'accuracy': score, 'approved_count': approved,
                   'scope': 'declared observation domain only; never production accuracy',
                   'reason': 'requires artifact integrity, actual training records, trusted human reviews and exact boolean predictions'},
        'regression': {'status': 'AVAILABLE_UNREVIEWED' if valid else 'BLOCKED', 'sample_count': len(samples) if valid else 0,
                       'accuracy': (sum(predictions[r['id']] == r['expected_false_success'] for r in samples)/len(samples)) if valid and prediction_valid else None,
                       'label_status': 'AI_AUTHORED_PENDING_HUMAN_REVIEW', 'independent_formal': False},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--expected-manifest-sha256', required=True)
    parser.add_argument('--training-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    paths = sorted(p for p in args.training_root.rglob('*') if p.suffix in {'.json', '.jsonl'} and p.is_file() and p.name not in {'manifest.json', 'quality_report.json'} and not p.name.endswith('report.json'))
    report = evaluate(args.manifest, args.expected_manifest_sha256, training_paths=paths)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'integrity': report['integrity']['status'], 'formal': report['formal']['status']}))
    return 0 if report['integrity']['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
