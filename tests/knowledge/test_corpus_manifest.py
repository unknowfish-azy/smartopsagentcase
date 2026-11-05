import json
import importlib
import pytest
from knowledge.corpus_manifest import build_manifest, verify_snapshot, export_bundle, restore_bundle, CorpusError

@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / 'corpus'
    root.mkdir()
    (root / 'a.md').write_text('Linux disk troubleshooting 磁盘空间', encoding='utf-8')
    return root

def test_deterministic_snapshot(corpus):
    manifest = build_manifest(corpus, 'v1')
    assert manifest == build_manifest(corpus, 'v1')
    snapshot = verify_snapshot(corpus, manifest, expected_version='v1', expected_hash=manifest['corpus_sha256'])
    (corpus / 'a.md').write_text('changed', encoding='utf-8')
    assert snapshot[0]['content'] == 'Linux disk troubleshooting 磁盘空间'

@pytest.mark.parametrize('change', ['missing', 'new', 'corrupt', 'utf8', 'escape', 'version', 'hash'])
def test_reject_changes(corpus, change):
    manifest = build_manifest(corpus, 'v1')
    if change == 'missing': (corpus / 'a.md').unlink()
    if change == 'new': (corpus / 'b.md').write_text('new')
    if change == 'corrupt': (corpus / 'a.md').write_text('bad')
    if change == 'utf8': (corpus / 'a.md').write_bytes(b'\xff')
    if change == 'escape': manifest['files'][0]['path'] = '../outside.md'
    with pytest.raises(CorpusError):
        verify_snapshot(corpus, manifest, expected_version='bad' if change == 'version' else None, expected_hash='0'*64 if change == 'hash' else None)

def test_roundtrip_and_no_overwrite(corpus, tmp_path):
    archive = tmp_path / 'backup.zip'
    export_bundle(corpus, 'v1', archive)
    target = tmp_path / 'restore'
    restore_bundle(archive, target)
    assert build_manifest(target, 'v1') == build_manifest(corpus, 'v1')
    with pytest.raises(CorpusError): restore_bundle(archive, target)

def test_manifest_readiness_fails_closed(corpus, tmp_path, monkeypatch):
    manifest = build_manifest(corpus, 'v1')
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    with monkeypatch.context() as isolated:
        isolated.setenv('KNOWLEDGE_REFERENCE_DIR', str(corpus))
        isolated.setenv('KNOWLEDGE_CORPUS_MANIFEST', str(path))
        isolated.setenv('KNOWLEDGE_CORPUS_VERSION', 'wrong')
        isolated.setenv('KNOWLEDGE_SEED_REFERENCE', '1')
        from fastapi.testclient import TestClient
        import knowledge.server as server
        server = importlib.reload(server)
        client = TestClient(server.app)
        assert client.get('/api/ready').status_code == 503
        client.post('/api/documents', json={'content': 'extra'})
        assert client.get('/api/ready').status_code == 503
    importlib.reload(server)

def test_restore_rejects_zip_escape(corpus, tmp_path):
    import zipfile
    target = tmp_path / 'restored'
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        output.writestr('manifest.json', json.dumps(build_manifest(corpus, 'v1')))
        output.writestr('corpus/../escape.md', 'escape')
    with pytest.raises(CorpusError): restore_bundle(archive, target)
    assert not target.exists()
    assert not (tmp_path / 'escape.md').exists()

def test_schema_and_duplicate_paths_rejected(corpus):
    manifest = build_manifest(corpus, 'v1')
    manifest['schema'] = 'unknown'
    with pytest.raises(CorpusError): verify_snapshot(corpus, manifest)
    manifest = build_manifest(corpus, 'v1')
    manifest['files'].append(manifest['files'][0])
    with pytest.raises(CorpusError): verify_snapshot(corpus, manifest)

def test_snapshot_reads_each_document_once(corpus, monkeypatch):
    from pathlib import Path
    manifest = build_manifest(corpus, 'v1')
    original = Path.read_bytes
    calls = []
    def read(path):
        calls.append(path)
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', read)
    docs = verify_snapshot(corpus, manifest)
    assert len(calls) == len(docs) == 1
