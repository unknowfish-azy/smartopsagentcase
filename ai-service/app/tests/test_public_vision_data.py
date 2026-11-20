"""公开视觉数据白名单下载器：策略闸门、清单落盘、校验与人工登记。

不联网：下载用注入的 fake opener，只验证白名单策略与文件/清单行为。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts import fetch_public_vision_data as svc

PAYLOAD = b"class_name,label\nPerson,/m/01g317\n"


class FakeResponse:
    def __init__(self, payload: bytes, url: str) -> None:
        self._payload = payload
        self._offset = 0
        self._url = url
        self.headers = {"Content-Length": str(len(payload))}
        self.status = 200

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def geturl(self) -> str:
        return self._url

    def read(self, size: int = -1) -> bytes:
        if self._offset >= len(self._payload):
            return b""
        end = len(self._payload) if size is None or size < 0 else self._offset + size
        chunk = self._payload[self._offset:end]
        self._offset += len(chunk)
        return chunk


class FakeOpener:
    def __init__(self, payload: bytes = PAYLOAD, url: str = "https://example.com/data.csv") -> None:
        self.payload = payload
        self.url = url
        self.calls: list[object] = []

    def __call__(self, request, timeout=None):
        self.calls.append(request)
        return FakeResponse(self.payload, self.url)


def _entry(**overrides):
    base = {
        "id": "demo_source",
        "dataset": "Demo",
        "kind": "annotations",
        "delivery": "http",
        "url": "https://example.com/data.csv",
        "filename": "data.csv",
        "license": "CC-BY-4.0",
        "license_url": "https://example.com/license",
        "verified": True,
        "class_map": {"Person": "person"},
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# 清单校验
# ---------------------------------------------------------------------------


def test_shipped_whitelist_is_valid_and_licensed():
    entries = svc.load_whitelist(svc.DEFAULT_WHITELIST)

    assert entries
    for entry in entries:
        assert entry["license"].strip()
        assert entry["license_url"].startswith("https://")
        if entry["delivery"] == "http":
            assert entry["url"].startswith("https://")

    by_id = {entry["id"]: entry for entry in entries}

    # person 是物体类；入侵是区域事件，不能混成一个检测类
    assert by_id["openimages_v7_train_bbox_annotations"]["class_map"] == {"Person": "person"}

    # 以下 URL 于 2026-11-20 对照官方下载页并实测 HTTP 200
    train = by_id["openimages_v7_train_bbox_annotations"]
    assert train["verified"] is True
    assert train["url"].endswith("/v6/oidv6-train-annotations-bbox.csv")

    validation = by_id["openimages_v7_validation_bbox_annotations"]
    assert validation["verified"] is True
    assert validation["url"].endswith("/v5/validation-annotations-bbox.csv")

    # COCO 官方只有 http 直链，必须走人工登记，不允许脚本自动下载
    for source_id in ("coco_2017_trainval_annotations", "coco_2017_val_images", "coco_2017_train_images"):
        assert by_id[source_id]["delivery"] == "manual"
        assert by_id[source_id]["url"].startswith("http://images.cocodataset.org/")

    # 至少有一条可直接下载的已核验条目，否则 --fetch all 是空操作
    assert any(entry["delivery"] == "http" and entry.get("verified") for entry in entries)


def test_validate_rejects_non_https_url():
    with pytest.raises(svc.WhitelistError, match="https"):
        svc.validate_entry(_entry(url="http://example.com/data.csv"))


def test_validate_rejects_missing_license():
    with pytest.raises(svc.WhitelistError, match="license"):
        svc.validate_entry(_entry(license=""))


def test_load_whitelist_rejects_duplicate_ids(tmp_path: Path):
    whitelist = tmp_path / "whitelist.json"
    whitelist.write_text(
        json.dumps({"sources": [_entry(), _entry()]}), encoding="utf-8"
    )
    with pytest.raises(svc.WhitelistError, match="重复"):
        svc.load_whitelist(whitelist)


# ---------------------------------------------------------------------------
# 下载闸门
# ---------------------------------------------------------------------------


def test_fetch_refuses_restricted_license(tmp_path: Path):
    with pytest.raises(svc.FetchError, match="allowlist"):
        svc.fetch_entry(_entry(license="research-only"), tmp_path, opener=FakeOpener())


def test_fetch_refuses_unverified_entry(tmp_path: Path):
    with pytest.raises(svc.FetchError, match="未核验"):
        svc.fetch_entry(_entry(verified=False), tmp_path, opener=FakeOpener())


def test_fetch_refuses_redirect_to_http(tmp_path: Path):
    opener = FakeOpener(url="http://example.com/data.csv")
    with pytest.raises(svc.FetchError, match="非 https"):
        svc.fetch_entry(_entry(), tmp_path, opener=opener)


def test_fetch_enforces_max_bytes(tmp_path: Path):
    with pytest.raises(svc.FetchError, match="max_bytes"):
        svc.fetch_entry(_entry(), tmp_path, max_bytes=4, opener=FakeOpener())


# ---------------------------------------------------------------------------
# 落盘 + 校验
# ---------------------------------------------------------------------------


def test_fetch_entry_writes_file_record_and_markdown(tmp_path: Path):
    opener = FakeOpener()

    record = svc.fetch_entry(_entry(), tmp_path, opener=opener)

    target = tmp_path / "demo_source" / "data.csv"
    assert target.read_bytes() == PAYLOAD
    assert record["sha256"] == hashlib.sha256(PAYLOAD).hexdigest()
    assert record["bytes"] == len(PAYLOAD)
    assert record["license"] == "CC-BY-4.0"
    assert record["class_map"] == {"Person": "person"}

    records = svc.load_records(tmp_path)
    assert [item["id"] for item in records] == ["demo_source"]

    markdown = (tmp_path / "SOURCES.md").read_text(encoding="utf-8")
    assert "Demo" in markdown
    assert "CC-BY-4.0" in markdown

    reports = svc.verify_records(tmp_path)
    assert [report["status"] for report in reports] == ["OK"]


def test_verify_detects_tampering(tmp_path: Path):
    svc.fetch_entry(_entry(), tmp_path, opener=FakeOpener())

    (tmp_path / "demo_source" / "data.csv").write_bytes(b"tampered")

    reports = svc.verify_records(tmp_path)
    assert reports[0]["status"] == "CHANGED"


def test_verify_reports_missing_file(tmp_path: Path):
    svc.fetch_entry(_entry(), tmp_path, opener=FakeOpener())
    (tmp_path / "demo_source" / "data.csv").unlink()

    assert svc.verify_records(tmp_path)[0]["status"] == "MISSING"


def test_upsert_replaces_same_id(tmp_path: Path):
    svc.fetch_entry(_entry(), tmp_path, opener=FakeOpener(PAYLOAD))
    svc.fetch_entry(_entry(), tmp_path, opener=FakeOpener(b"second"))

    records = svc.load_records(tmp_path)
    assert len(records) == 1
    assert records[0]["bytes"] == len(b"second")


# ---------------------------------------------------------------------------
# 人工登记
# ---------------------------------------------------------------------------


def test_register_file_records_external_path(tmp_path: Path):
    dataset = tmp_path / "dfire.zip"
    dataset.write_bytes(b"fake-zip")

    record = svc.register_file(
        dataset,
        dataset="D-Fire",
        license_id="CC-BY-4.0",
        license_url="https://example.com/license",
        class_map={"fire": "fire_or_smoke", "smoke": "fire_or_smoke"},
        out_dir=tmp_path / "out",
    )

    assert record["id"] == "d_fire_dfire"
    assert Path(record["path"]).is_absolute()
    assert svc.verify_records(tmp_path / "out")[0]["status"] == "OK"


def test_register_refuses_restricted_license(tmp_path: Path):
    dataset = tmp_path / "x.zip"
    dataset.write_bytes(b"x")

    with pytest.raises(svc.FetchError, match="allowlist"):
        svc.register_file(
            dataset,
            dataset="Unknown",
            license_id="unknown",
            license_url="https://example.com",
            out_dir=tmp_path / "out",
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_list_and_unknown_id(tmp_path: Path, capsys):
    assert svc.main(["--list"]) == 0
    assert "openimages_v7_train_bbox_annotations" in capsys.readouterr().out

    assert svc.main(["--fetch", "not_in_whitelist"]) == 2


def test_probe_skips_manual_and_reports_http(tmp_path: Path):
    manual = svc.probe(_entry(delivery="manual", url=None, filename=None))
    assert manual["status"] == "MANUAL"

    result = svc.probe(_entry(), opener=FakeOpener())
    assert result["status"] == "OK"
    assert result["content_length"] == len(PAYLOAD)


def test_probe_reports_failure_without_raising():
    def broken(request, timeout=None):
        raise OSError("network down")

    result = svc.probe(_entry(), opener=broken)
    assert result["status"] == "FAILED"
    assert "network down" in result["detail"]
