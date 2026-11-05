import hashlib
import json
import pytest
from training.independent_benchmark import evaluate


def dump(path, value):
    path.write_text(json.dumps(value), encoding='utf-8')
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(tmp_path, change=None):
    evidence = tmp_path / 'probe.json'
    eh = dump(evidence, {'status': 502, 'body': 'controlled', 'url': 'http://127.0.0.1:12345/test', 'mode': 'CONTROLLED', 'outcome': 'http_error', 'claim': 'request succeeded', 'expected_false_success': True})
    sample = {'id': 'new-1', 'input': 'observe local gateway', 'incident_family': 'controlled-gateway',
              'split': 'test', 'origin': 'CONTROLLED', 'derived_from_candidate': False,
              'label_status': 'pending_review', 'expected_false_success': True,
              'claim': 'request succeeded', 'evidence': {'path': 'probe.json', 'sha256': eh}}
    samples = [sample]
    if change:
        change(samples)
    sh = dump(tmp_path / 'samples.json', samples)
    mh = dump(tmp_path / 'manifest.json', {'schema_version': 'independent-v1', 'samples_path': 'samples.json', 'samples_sha256': sh})
    return tmp_path / 'manifest.json', mh


def test_pending_labels_block_formal_but_keep_regression(tmp_path):
    path, digest = fixture(tmp_path)
    result = evaluate(path, digest)
    assert result['formal']['status'] == 'BLOCKED'
    assert result['formal']['accuracy'] is None
    assert result['formal']['approved_count'] == 0
    assert result['regression']['sample_count'] == 1


@pytest.mark.parametrize('kind', ['manifest', 'samples', 'probe'])
def test_tampering_blocks_scoring(tmp_path, kind):
    path, digest = fixture(tmp_path)
    target = {'manifest': path, 'samples': tmp_path/'samples.json', 'probe': tmp_path/'probe.json'}[kind]
    target.write_text(target.read_text() + ' ', encoding='utf-8')
    result = evaluate(path, digest)
    assert result['integrity']['status'] == 'BLOCKED'
    assert result['formal']['accuracy'] is None


@pytest.mark.parametrize('change', [
    lambda s: s.append(dict(s[0])),
    lambda s: s[0].update(expected_false_success='yes'),
    lambda s: s[0].update(derived_from_candidate=True),
    lambda s: s[0]['evidence'].update(path='../outside.json'),
    lambda s: s[0].update(label_status='approved'),
])
def test_invalid_or_self_approved_samples_rejected(tmp_path, change):
    path, digest = fixture(tmp_path, change)
    assert evaluate(path, digest)['integrity']['status'] == 'BLOCKED'


@pytest.mark.parametrize('field,value', [('input', 'observe local gateway'), ('incident_family', 'controlled-gateway')])
def test_training_overlap_checked_from_records_not_manifest_flags(tmp_path, field, value):
    path, digest = fixture(tmp_path)
    training = tmp_path / 'training.json'
    dump(training, [dict({'input': 'other prompt', 'incident_family': 'other-family'}, **{field: value})])
    result = evaluate(path, digest, training_paths=[training])
    assert result['integrity']['status'] == 'BLOCKED'
    assert any('leakage' in reason for reason in result['integrity']['reasons'])


def test_capture_observes_real_loopback_http_boundaries(tmp_path):
    from scripts.research.capture_independent_probes import capture
    manifest, digest = capture(tmp_path / 'dataset')
    result = evaluate(manifest, digest)
    samples = json.loads((manifest.parent / 'samples.json').read_text())
    probes = [json.loads((manifest.parent / s['evidence']['path']).read_text()) for s in samples]
    assert len(samples) >= 8
    assert {200, 401, 403, 502, 504}.issubset({p.get('status') for p in probes})
    assert any(p['outcome'] == 'timeout' for p in probes)
    assert all(p['url'].startswith('http://127.0.0.1:') for p in probes)
    assert result['integrity']['status'] == 'PASS'
    assert result['formal']['accuracy'] is None


@pytest.mark.parametrize('payload', [{}, [], {'schema_version': 'manifest', 'sample_count': 12}, [{'unknown': 'record'}]])
def test_empty_and_control_training_json_is_not_leakage_evidence(tmp_path, payload):
    path, digest = fixture(tmp_path)
    train = tmp_path / 'train.json'
    dump(train, payload)
    result = evaluate(path, digest, training_paths=[train])
    assert result['leakage']['status'] != 'PASS'
    assert result['integrity']['status'] == 'BLOCKED'


@pytest.mark.parametrize('record', [
    {'messages': [{'role': 'user', 'content': 'observe local gateway'}], 'metadata': {'incident_family': 'different'}},
    {'instruction': 'different', 'metadata': {'incident_family': 'controlled-gateway'}},
])
def test_nested_and_chat_training_leakage(tmp_path, record):
    path, digest = fixture(tmp_path)
    train = tmp_path / 'train.json'
    dump(train, [record])
    result = evaluate(path, digest, training_paths=[train])
    assert result['integrity']['status'] == 'BLOCKED'
    assert any('leakage' in x for x in result['integrity']['reasons'])


def test_manifest_array_is_blocked_without_throwing(tmp_path):
    path, _ = fixture(tmp_path)
    digest = dump(path, [])
    assert evaluate(path, digest)['integrity']['status'] == 'BLOCKED'


@pytest.mark.parametrize('probe', [{}, {'status': 200}, {'status': 502, 'body': '', 'url': 'https://example.com', 'outcome': 'http_error', 'mode': 'CONTROLLED'}])
def test_hash_matching_non_probe_is_rejected(tmp_path, probe):
    path, _ = fixture(tmp_path)
    samples = json.loads((tmp_path / 'samples.json').read_text())
    samples[0]['evidence']['sha256'] = dump(tmp_path / 'probe.json', probe)
    sh = dump(tmp_path / 'samples.json', samples)
    digest = dump(path, {'schema_version': 'independent-v1', 'samples_path': 'samples.json', 'samples_sha256': sh})
    assert evaluate(path, digest)['integrity']['status'] == 'BLOCKED'


def test_each_artifact_is_read_once(tmp_path, monkeypatch):
    path, digest = fixture(tmp_path)
    original = type(path).read_bytes
    counts = {}
    def read_once(self):
        counts[str(self)] = counts.get(str(self), 0) + 1
        return original(self)
    monkeypatch.setattr(type(path), 'read_bytes', read_once)
    assert evaluate(path, digest)['integrity']['status'] == 'PASS'
    assert len(counts) == 3
    assert set(counts.values()) == {1}


def test_non_string_probe_url_is_blocked(tmp_path):
    path, _ = fixture(tmp_path)
    probe = json.loads((tmp_path/'probe.json').read_text())
    probe['url'] = {}
    rows = json.loads((tmp_path/'samples.json').read_text())
    rows[0]['evidence']['sha256'] = dump(tmp_path/'probe.json', probe)
    digest = dump(path, {'schema_version':'independent-v1','samples_path':'samples.json','samples_sha256':dump(tmp_path/'samples.json', rows)})
    assert evaluate(path, digest)['integrity']['status'] == 'BLOCKED'
