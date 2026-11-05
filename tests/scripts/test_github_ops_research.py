import base64
import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('ops_research', Path(__file__).parents[2] / 'scripts/research/fetch_github_ops_data.py')
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def test_evidence_is_pinned_and_license_bytes_are_saved(tmp_path):
    calls = []
    def fake_fetch(opener, url):
        calls.append(url)
        if url.endswith('/commits/main'):
            return {'sha': 'a' * 40}
        if '/readme?' in url:
            return {'sha': 'readmeblob', 'path': 'README.md', 'content': base64.b64encode(b'readme').decode()}
        if '/license?' in url:
            return {'sha': 'licenseblob', 'path': 'LICENSE', 'content': base64.b64encode(b'terms').decode()}
        return {'default_branch': 'main', 'full_name': 'owner/repo'}
    row = module.collect_repository(None, 'owner/repo', tmp_path, fetcher=fake_fetch)
    assert row['commit_sha'] == 'a' * 40
    assert all('ref=' + 'a' * 40 in url for url in calls if '/readme?' in url or '/license?' in url)
    assert Path(row['license_file']['local_path']).read_bytes() == b'terms'
    assert row['data_license_status'] == 'manual_review_required'


def test_missing_license_is_explicit_not_assumed(tmp_path):
    def fake_fetch(opener, url):
        if '/license?' in url:
            raise ValueError('missing')
        if '/commits/' in url:
            return {'sha': 'b' * 40}
        if '/readme?' in url:
            return {'sha': 'r', 'content': base64.b64encode(b'hi').decode()}
        return {'default_branch': 'main'}
    row = module.collect_repository(None, 'owner/repo', tmp_path, fetcher=fake_fetch)
    assert row['license_file']['status'] == 'unavailable'
    assert row['data_license_status'] == 'manual_review_required'
