import hashlib
import json

import pytest

from scripts.backup import build_manifest as manifest_tool


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def components(tmp_path):
    (tmp_path / "attachments").mkdir()
    (tmp_path / "attachments" / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "attachments" / "b.txt").write_text("bravo", encoding="utf-8")
    (tmp_path / "audit").mkdir()
    (tmp_path / "audit" / "audit.jsonl").write_text('{"event":1}\n', encoding="utf-8")
    (tmp_path / "smartops.sql.gz").write_bytes(b"db-dump")
    (tmp_path / "knowledge.json").write_text('{"docs":0}', encoding="utf-8")
    (tmp_path / "keys").mkdir()
    (tmp_path / "keys" / "k1").write_text("key-material", encoding="utf-8")
    return {
        "DATABASE": tmp_path / "smartops.sql.gz",
        "ATTACHMENTS": tmp_path / "attachments",
        "KNOWLEDGE_MANIFEST": tmp_path / "knowledge.json",
        "AUDIT": tmp_path / "audit",
        "KEYS": tmp_path / "keys",
    }


def test_manifest_hashes_files_and_directories(components):
    manifest = manifest_tool.build_manifest("prod-core", "2026-11-06T01:00:00Z", components)

    assert manifest["schema"] == "smartops-backup/v1"
    assert manifest["set"] == "prod-core"
    artifacts = {artifact["component"]: artifact for artifact in manifest["artifacts"]}
    assert set(artifacts) == set(manifest_tool.REQUIRED_COMPONENTS)

    database = artifacts["DATABASE"]
    assert database["sha256"] == _sha256(components["DATABASE"])
    assert database["bytes"] == len(b"db-dump")
    assert database["itemCount"] == 1

    attachments = artifacts["ATTACHMENTS"]
    assert attachments["itemCount"] == 2
    assert attachments["bytes"] == len(b"alpha") + len(b"bravo")
    expected = hashlib.sha256(
        (f"a.txt:{_sha256(components['ATTACHMENTS'] / 'a.txt')}\n"
         f"b.txt:{_sha256(components['ATTACHMENTS'] / 'b.txt')}").encode("utf-8")
    ).hexdigest()
    assert attachments["sha256"] == expected


def test_directory_digest_is_deterministic(components):
    first = manifest_tool.build_manifest("prod-core", "2026-11-06T01:00:00Z", components)
    second = manifest_tool.build_manifest("prod-core", "2026-11-06T01:00:00Z", components)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_manifest_refuses_incomplete_set_without_override(components, tmp_path, capsys):
    code = manifest_tool.main([
        "--set", "prod-core", "--output", str(tmp_path / "manifest.json"),
        "--component", f"DATABASE={components['DATABASE']}",
    ])
    assert code == 2
    assert "缺少必需组件" in capsys.readouterr().err


def test_manifest_allows_partial_with_override(components, tmp_path):
    code = manifest_tool.main([
        "--set", "prod-core", "--output", str(tmp_path / "manifest.json"), "--allow-partial",
        "--component", f"DATABASE={components['DATABASE']}",
    ])
    assert code == 0
    written = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert [artifact["component"] for artifact in written["artifacts"]] == ["DATABASE"]


def test_manifest_rejects_unknown_component(components, tmp_path, capsys):
    code = manifest_tool.main([
        "--set", "prod-core", "--output", str(tmp_path / "manifest.json"),
        "--component", f"SECRETS={components['DATABASE']}",
    ])
    assert code == 2
    assert "未知组件" in capsys.readouterr().err
