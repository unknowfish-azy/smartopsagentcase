"""视觉数据蒸馏与 YOLO 导出的纯函数测试。

这些断言锁的是三件事：
1. 蒸馏只做它能证明的事（sha256 精确去重），不虚报"近似去重"；
2. 每一类丢弃都有可核对的 reason，数量对得上；
3. 写出的 YOLO 目录能被 ultralytics 直接吃（images/ labels/ data.yaml 齐备）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vision.classes import CLASS_PRESETS, resolve_classes
from app.vision.dataset import (
    dedupe,
    filter_frames,
    normalize_frame_row,
    read_jsonl,
    split_by_time,
    stratified_sample,
    write_jsonl,
    write_yolo_dataset,
)


def record(frame_id: int, *, sha: str = "", size: int = 2048, target: str = "配电柜A",
           device: str = "robot-01", captured_at: str = "2026-11-17T10:00:00") -> dict:
    return {
        "frame_id": frame_id,
        "device_key": device,
        "target": target,
        "file_path": f"/tmp/frame-{frame_id}.jpg",
        "sha256": sha or f"hash{frame_id:04d}",
        "bytes": size,
        "width": 640,
        "height": 480,
        "quality": "low",
        "captured_at": captured_at,
        "simulated": False,
    }


class TestNormalize:
    def test_resolves_relative_path_against_frames_root(self, tmp_path: Path):
        row = normalize_frame_row(
            {"frame_id": 7, "device_key": "robot-01", "file_path": "2026-11-17/robot-01/abc.jpg",
             "sha256": "abc", "bytes": 100, "target": None, "width": 10, "height": 20,
             "quality": "low", "captured_at": "2026-11-17T10:00:00", "simulated": 1},
            root=tmp_path,
        )
        assert Path(row["file_path"]) == (tmp_path / "2026-11-17/robot-01/abc.jpg").resolve()
        assert row["target"] is None
        assert row["simulated"] is True
        assert row["bytes"] == 100

    def test_missing_file_path_is_rejected_not_defaulted(self):
        with pytest.raises(ValueError, match="file_path"):
            normalize_frame_row({"frame_id": 1, "device_key": "robot-01"})


class TestDedupe:
    def test_identical_sha_keeps_first_and_reports_drop(self):
        kept, dropped = dedupe([record(1, sha="same"), record(2, sha="same"), record(3, sha="other")])
        assert [item["frame_id"] for item in kept] == [1, 3]
        assert dropped[0]["drop_reason"] == "DUPLICATE_SHA256"
        assert dropped[0]["frame_id"] == 2

    def test_missing_sha_is_dropped_with_reason(self):
        kept, dropped = dedupe([{**record(9), "sha256": ""}])
        assert kept == []
        assert dropped[0]["drop_reason"] == "MISSING_SHA256"


class TestFilter:
    def test_size_bounds(self):
        kept, dropped = filter_frames(
            [record(1, size=10), record(2, size=5000), record(3, size=99_999_999)],
            min_bytes=1024, max_bytes=8 * 1024 * 1024,
        )
        assert [item["frame_id"] for item in kept] == [2]
        reasons = sorted(item["drop_reason"].split(":")[0] for item in dropped)
        assert reasons == ["TOO_LARGE", "TOO_SMALL"]


class TestStratified:
    def test_zero_limits_mean_unlimited(self):
        records = [record(index) for index in range(5)]
        kept, dropped = stratified_sample(records, 0, 0)
        assert len(kept) == 5 and dropped == []

    def test_per_target_limit_spreads_over_time(self):
        # 同一 target 的 10 帧，限量 3：应覆盖首、中、尾而不是只取前 3 帧
        records = [record(index, captured_at=f"2026-11-17T10:{index:02d}:00") for index in range(10)]
        kept, dropped = stratified_sample(records, per_target_limit=3, per_device_limit=0)
        assert len(kept) == 3
        assert len(dropped) == 7
        picked = [item["captured_at"][-5:-3] for item in kept]
        assert picked[0] == "00" and picked[-1] == "09"  # 时间跨度两端都在

    def test_limits_are_applied_per_bucket_independently(self):
        records = [record(index, target="A") for index in range(4)]
        records += [record(index + 100, target="B", captured_at="2026-11-17T11:00:00") for index in range(4)]
        kept, _ = stratified_sample(records, per_target_limit=2, per_device_limit=0)
        assert sum(1 for item in kept if item["target"] == "A") == 2
        assert sum(1 for item in kept if item["target"] == "B") == 2

    def test_device_limit_applies_after_target_limit(self):
        records = [record(index, device="r1") for index in range(6)]
        kept, dropped = stratified_sample(records, per_target_limit=0, per_device_limit=2)
        assert len(kept) == 2
        assert len(dropped) == 4


class TestSplit:
    def test_time_based_split_puts_latest_in_val(self):
        records = [record(index, captured_at=f"2026-11-17T10:0{index}:00") for index in range(10)]
        splits = split_by_time(records, val_ratio=0.2)
        assert len(splits["train"]) == 8 and len(splits["val"]) == 2
        assert splits["val"][-1]["frame_id"] == 9  # 最新的在验证集
        assert splits["train"][0]["frame_id"] == 0

    def test_single_frame_stays_in_train(self):
        splits = split_by_time([record(1)], val_ratio=0.2)
        assert len(splits["train"]) == 1 and splits["val"] == []

    def test_zero_val_ratio_keeps_everything_in_train(self):
        records = [record(index) for index in range(4)]
        splits = split_by_time(records, val_ratio=0.0)
        assert len(splits["train"]) == 4 and splits["val"] == []


class TestWriteYolo:
    def _make_frames(self, tmp_path: Path, count: int) -> list[dict]:
        records = []
        for index in range(count):
            image = tmp_path / f"src-{index}.jpg"
            image.write_bytes(b"\xff\xd8\xff\xe0" + bytes([index]) * 64)
            item = record(index, captured_at=f"2026-11-17T10:0{index}:00")
            item["file_path"] = str(image)
            records.append(item)
        return records

    def test_writes_images_labels_and_data_yaml(self, tmp_path: Path):
        records = self._make_frames(tmp_path, 4)
        out = tmp_path / "yolo"
        result = write_yolo_dataset(split_by_time(records, 0.25), out, ["person", "bottle"], preset="coco_subset")

        assert result["counts"] == {"train": 3, "val": 1}
        assert len(list((out / "images/train").glob("*.jpg"))) == 3
        assert len(list((out / "images/val").glob("*.jpg"))) == 1
        # label 是空文件（负样本），不是缺失
        labels = list((out / "labels/train").glob("*.txt"))
        assert len(labels) == 3
        assert all(item.read_text(encoding="utf-8") == "" for item in labels)

        data_yaml = (out / "data.yaml").read_text(encoding="utf-8")
        assert "train: images/train" in data_yaml
        assert "val: images/val" in data_yaml
        assert "  0: person" in data_yaml and "  1: bottle" in data_yaml
        assert result["preset"] == "coco_subset"

    def test_manifest_traceability(self, tmp_path: Path):
        records = self._make_frames(tmp_path, 2)
        out = tmp_path / "yolo"
        write_yolo_dataset(split_by_time(records, 0.5), out, ["person"])
        manifest = read_jsonl(out / "manifest.jsonl")
        assert len(manifest) == 2
        assert all("yolo_image" in item and "split" in item for item in manifest)

    def test_missing_source_file_is_skipped_and_marked(self, tmp_path: Path):
        records = self._make_frames(tmp_path, 2)
        records[0]["file_path"] = str(tmp_path / "gone.jpg")
        out = tmp_path / "yolo"
        result = write_yolo_dataset({"train": records, "val": []}, out, ["person"])
        assert result["counts"]["train"] == 1
        assert records[0]["copy_status"] == "MISSING_FILE"


class TestClasses:
    def test_presets_have_unique_names_and_stable_order(self):
        for name, classes in CLASS_PRESETS.items():
            assert classes, f"{name} 不能为空"
            assert len(classes) == len(set(classes)), f"{name} 有重复类别"

    def test_default_preset_when_none(self):
        name, classes = resolve_classes(None)
        assert name == "coco_subset"
        assert classes[0] == "person"  # 顺序即 class id，不能随便动

    def test_unknown_preset_raises_with_available_list(self):
        with pytest.raises(ValueError, match="coco_subset"):
            resolve_classes("no_such_preset")

    def test_custom_json_file(self, tmp_path: Path):
        custom = tmp_path / "my_classes.json"
        custom.write_text(json.dumps({"name": "mine", "classes": ["a", "b"]}), encoding="utf-8")
        name, classes = resolve_classes(str(custom))
        assert name == "mine" and classes == ["a", "b"]

    def test_duplicate_class_in_file_is_rejected(self, tmp_path: Path):
        custom = tmp_path / "bad.json"
        custom.write_text(json.dumps(["a", "a"]), encoding="utf-8")
        with pytest.raises(ValueError, match="重复"):
            resolve_classes(str(custom))


class TestJsonl:
    def test_roundtrip(self, tmp_path: Path):
        path = tmp_path / "nested" / "items.jsonl"
        write_jsonl([{"a": 1}, {"b": "中文"}], path)
        assert read_jsonl(path) == [{"a": 1}, {"b": "中文"}]

    def test_bad_line_reports_line_number(self, tmp_path: Path):
        path = tmp_path / "bad.jsonl"
        path.write_text('{"ok": 1}\nnot-json\n', encoding="utf-8")
        with pytest.raises(ValueError, match="第 2 行"):
            read_jsonl(path)
