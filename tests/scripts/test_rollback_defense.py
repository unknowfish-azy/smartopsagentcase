import hashlib
import json
import zipfile

import pytest

from scripts.rollback_defense import rollback


def make_bundle(root, bundle):
    files = []
    for path, current, before in [("existing.txt", b"after", b"before"), ("new.txt", b"new", None)]:
        (root / path).write_bytes(current)
        files.append({"path": path, "after_sha256": hashlib.sha256(current).hexdigest(),
                      "before_sha256": hashlib.sha256(before).hexdigest() if before else None})
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"baseline": "test snapshot", "files": files}))
        archive.writestr("before/existing.txt", b"before")


def test_rollback_defaults_to_read_only_then_preserves_current_files(tmp_path):
    bundle = tmp_path / "rollback.zip"
    make_bundle(tmp_path, bundle)
    rollback(tmp_path, bundle)
    assert (tmp_path / "existing.txt").read_bytes() == b"after"
    assert (tmp_path / "new.txt").read_bytes() == b"new"
    rollback(tmp_path, bundle, apply=True)
    assert (tmp_path / "existing.txt").read_bytes() == b"before"
    assert not (tmp_path / "new.txt").exists()
    assert next((tmp_path / ".runtime/defense-rollback").rglob("new.txt")).read_bytes() == b"new"


def test_rollback_checks_all_hashes_before_restoring_any_file(tmp_path):
    bundle = tmp_path / "rollback.zip"
    make_bundle(tmp_path, bundle)
    (tmp_path / "new.txt").write_bytes(b"later user change")
    with pytest.raises(ValueError, match="changed since delivery"):
        rollback(tmp_path, bundle, apply=True)
    assert (tmp_path / "existing.txt").read_bytes() == b"after"
    assert (tmp_path / "new.txt").read_bytes() == b"later user change"
