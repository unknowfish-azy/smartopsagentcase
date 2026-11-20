"""Open Images Person 子集构造：过滤口径、YOLO 转换、逐图记账。

不联网：下载器注入 fake，只验证纯函数与落盘结构。
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from app.vision.dataset import read_data_yaml
from scripts import build_openimages_person_subset as sub

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 16
ANNOTATION_HEADER = [
    "ImageID", "Source", "LabelName", "Confidence", "XMin", "XMax", "YMin", "YMax",
    "IsOccluded", "IsTruncated", "IsGroupOf", "IsDepiction", "IsInside",
]
IMAGE_HEADER = [
    "ImageID", "Subset", "OriginalURL", "OriginalLandingURL", "License",
    "AuthorProfileURL", "Author", "Title", "OriginalSize", "OriginalMD5",
    "Thumbnail300KURL", "Rotation",
]


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)
    return path


def _annotation(image_id="img1", mid="/m/01g317", **overrides):
    row = {
        "ImageID": image_id, "Source": "xclick", "LabelName": mid, "Confidence": "1",
        "XMin": "0.1", "XMax": "0.5", "YMin": "0.2", "YMax": "0.6",
        "IsOccluded": "0", "IsTruncated": "0", "IsGroupOf": "0",
        "IsDepiction": "0", "IsInside": "0",
    }
    row.update(overrides)
    return [row[column] for column in ANNOTATION_HEADER]


def _image_row(image_id="img1", url="https://example.com/a.jpg", license_id="https://creativecommons.org/licenses/by/2.0/", rotation=""):
    row = {
        "ImageID": image_id, "Subset": "validation", "OriginalURL": url,
        "OriginalLandingURL": "https://example.com", "License": license_id,
        "AuthorProfileURL": "", "Author": "a", "Title": "t", "OriginalSize": "100",
        "OriginalMD5": "abc", "Thumbnail300KURL": "", "Rotation": rotation,
    }
    return [row[column] for column in IMAGE_HEADER]


class FakeDownloader:
    def __init__(self, payload: bytes = JPEG) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def __call__(self, url, dest: Path, *, timeout, max_bytes):
        self.calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(self.payload)
        return hashlib.sha256(self.payload).hexdigest(), len(self.payload)


# ---------------------------------------------------------------------------
# 标注过滤
# ---------------------------------------------------------------------------


def test_load_annotations_filters_groupof_depiction_and_unverified(tmp_path: Path):
    path = _write_csv(tmp_path / "a.csv", ANNOTATION_HEADER, [
        _annotation(),
        _annotation(Confidence="0"),
        _annotation(IsGroupOf="1"),
        _annotation(IsDepiction="1"),
        _annotation(XMax="0.1"),          # 退化框
        _annotation(mid="/m/02rdsp"),     # 非 person 类
    ])

    images, skipped = sub.load_annotations(path, ("Person",))

    assert len(images["img1"]) == 1
    assert skipped["unverified"] == 1
    assert skipped["group_of"] == 1
    assert skipped["depiction"] == 1
    assert skipped["degenerate"] == 1


def test_dedupe_merges_person_and_gendered_boxes():
    boxes = [
        sub.Box("Person", 0.1, 0.1, 0.5, 0.5),
        sub.Box("Man", 0.1, 0.1, 0.5, 0.5),
        sub.Box("Woman", 0.6, 0.6, 0.8, 0.9),
    ]

    kept = sub.dedupe_boxes(boxes)

    assert len(kept) == 2
    assert {box.label for box in kept} == {"Person", "Woman"}


def test_to_yolo_lines_uses_normalized_center_format():
    lines = sub.to_yolo_lines([sub.Box("Person", 0.1, 0.2, 0.5, 0.6)])

    assert lines == ["0 0.300000 0.400000 0.400000 0.400000"]


# ---------------------------------------------------------------------------
# 选图闸门
# ---------------------------------------------------------------------------


def test_select_images_applies_https_license_and_rotation(tmp_path: Path):
    annotations = {"a": [sub.Box("Person", 0.1, 0.1, 0.2, 0.2)]}
    annotations.update({key: annotations["a"] for key in ("b", "c", "d", "e")})
    meta = {
        "a": {"url": "https://ok/a.jpg", "license": sub.DEFAULT_ALLOWED_LICENSES[0],
              "rotation": "", "md5": "", "size": 1},
        "b": {"url": "http://plain/b.jpg", "license": sub.DEFAULT_ALLOWED_LICENSES[0],
              "rotation": "", "md5": "", "size": 1},
        "c": {"url": "https://ok/c.jpg", "license": "https://creativecommons.org/licenses/by-sa/2.0/",
              "rotation": "", "md5": "", "size": 1},
        "d": {"url": "https://ok/d.jpg", "license": sub.DEFAULT_ALLOWED_LICENSES[0],
              "rotation": "90", "md5": "", "size": 1},
        "e": None,
    }
    meta.pop("e")

    selected, skipped = sub.select_images(annotations, meta, limit=10)

    assert [image_id for image_id, _, _ in selected] == ["a"]
    assert skipped["non_https"] == 1
    assert skipped["license_not_allowed"] == 1
    assert skipped["rotated"] == 1
    assert skipped["no_meta"] == 1


# ---------------------------------------------------------------------------
# 落盘
# ---------------------------------------------------------------------------


def test_build_writes_yolo_dataset_and_provenance(tmp_path: Path):
    annotations = _write_csv(tmp_path / "a.csv", ANNOTATION_HEADER, [_annotation()])
    image_list = _write_csv(tmp_path / "i.csv", IMAGE_HEADER, [_image_row()])
    downloader = FakeDownloader()

    summary = sub.build(
        annotations, image_list, tmp_path / "ds",
        limit=5, val_ratio=0.0, downloader=downloader,
    )

    assert summary["downloaded"] == 1
    assert summary["failed"] == 0

    image_path = tmp_path / "ds/images/train/img1.jpg"
    label_path = tmp_path / "ds/labels/train/img1.txt"
    assert image_path.read_bytes() == JPEG
    assert label_path.read_text(encoding="utf-8") == "0 0.300000 0.400000 0.400000 0.400000\n"

    parsed = read_data_yaml(tmp_path / "ds/data.yaml")
    assert parsed["classes"] == ["person"]
    assert parsed["root"].resolve() == (tmp_path / "ds").resolve()
    assert parsed["splits"]["train"].name == "train"

    records = [
        json.loads(line)
        for line in (tmp_path / "ds/manifest.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["status"] == "DOWNLOADED"
    assert records[0]["license"] == sub.DEFAULT_ALLOWED_LICENSES[0]
    assert records[0]["sha256"] == hashlib.sha256(JPEG).hexdigest()

    source = json.loads((tmp_path / "ds/SOURCE.json").read_text(encoding="utf-8"))
    assert source["counts"]["downloaded"] == 1
    assert source["classes"] == ["Person"]


def test_build_reuses_existing_image_without_redownload(tmp_path: Path):
    annotations = _write_csv(tmp_path / "a.csv", ANNOTATION_HEADER, [_annotation()])
    image_list = _write_csv(tmp_path / "i.csv", IMAGE_HEADER, [_image_row()])
    existing = tmp_path / "ds/images/train/img1.jpg"
    existing.parent.mkdir(parents=True)
    existing.write_bytes(JPEG)

    def exploding(*args, **kwargs):
        raise AssertionError("已存在的图片不应重新下载")

    summary = sub.build(
        annotations, image_list, tmp_path / "ds",
        limit=5, val_ratio=0.0, downloader=exploding,
    )

    assert summary["reused"] == 1
    assert summary["downloaded"] == 0


def test_build_marks_non_image_payload_as_failed(tmp_path: Path):
    annotations = _write_csv(tmp_path / "a.csv", ANNOTATION_HEADER, [_annotation()])
    image_list = _write_csv(tmp_path / "i.csv", IMAGE_HEADER, [_image_row()])

    summary = sub.build(
        annotations, image_list, tmp_path / "ds",
        limit=5, val_ratio=0.0, downloader=FakeDownloader(payload=b"<html>404</html>"),
    )

    assert summary["failed"] == 1
    assert not (tmp_path / "ds/images/train/img1.jpg").exists()
    assert not (tmp_path / "ds/labels/train/img1.txt").exists()

    record = json.loads((tmp_path / "ds/manifest.jsonl").read_text(encoding="utf-8").strip())
    assert record["status"] == "FAILED"
    assert "不是图片" in record["error"]


def test_build_dry_run_writes_nothing(tmp_path: Path):
    annotations = _write_csv(tmp_path / "a.csv", ANNOTATION_HEADER, [_annotation()])
    image_list = _write_csv(tmp_path / "i.csv", IMAGE_HEADER, [_image_row()])

    summary = sub.build(annotations, image_list, tmp_path / "ds", dry_run=True)

    assert summary["selected"] == 1
    assert summary["boxes"] == 1
    assert not (tmp_path / "ds").exists()


def test_build_rejects_unknown_class(tmp_path: Path):
    annotations = _write_csv(tmp_path / "a.csv", ANNOTATION_HEADER, [_annotation()])
    image_list = _write_csv(tmp_path / "i.csv", IMAGE_HEADER, [_image_row()])

    with pytest.raises(sub.SubsetError, match="不支持的类"):
        sub.build(annotations, image_list, tmp_path / "ds", classes=("Cat",))
