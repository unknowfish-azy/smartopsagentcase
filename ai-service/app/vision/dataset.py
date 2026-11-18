"""关键帧蒸馏与 YOLO 数据集落盘。

整条链路（对应脚本三个子命令）：

    robot_frame（DB） --normalize--> 原始清单
                                   --dedupe/filter--> 干净清单
                                   --stratified_sample--> 蒸馏清单
                                   --split_by_time--> train/val
                                   --write_yolo_dataset--> images/ labels/ data.yaml

三条原则（沿用 `app/training/dataset.py`）：
1. 除 `write_yolo_dataset` 外全是纯函数，pytest 可直接喂小样本；
2. 每个环节都返回"丢掉了什么、为什么丢"，禁止把跳过伪装成成功；
3. 不推断缺失字段，也不编造标注——没有标注的图就是负样本（空 label），
   真实框要由外部标注工具补齐。

为什么切分按时间而不是随机：
机器人关键帧在时间上高度相关（相隔 2s 的两帧几乎一样），随机切分会让
验证集里混入训练集的"近邻帧"，指标虚高。按时间切最接近上线后的真实分布。
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Iterable, Sequence

# 与 robot_frame 表列口径一致
FRAME_FIELDS = (
    "frame_id",
    "device_key",
    "target",
    "file_path",
    "sha256",
    "bytes",
    "width",
    "height",
    "quality",
    "captured_at",
    "simulated",
)


def normalize_frame_row(row: dict[str, Any], root: Path | str = ".") -> dict[str, Any]:
    """把 DB 行规整成清单记录；`file_path` 是相对 `root` 的路径，这里解析成绝对路径。"""
    file_path = row.get("file_path")
    if not file_path:
        raise ValueError(f"frame {row.get('frame_id')} 缺 file_path")
    absolute = (Path(root) / str(file_path)).resolve()
    return {
        "frame_id": row.get("frame_id") or row.get("id"),
        "device_key": str(row.get("device_key") or "unknown"),
        "target": (str(row["target"]) if row.get("target") else None),
        "file_path": str(absolute),
        "sha256": str(row.get("sha256") or ""),
        "bytes": int(row.get("bytes") or 0),
        "width": row.get("width"),
        "height": row.get("height"),
        "quality": row.get("quality"),
        # ISO 字符串：字典序即时间序，切分时不用再解析
        "captured_at": str(row.get("captured_at") or ""),
        "simulated": bool(row.get("simulated") or 0),
    }


def dedupe(records: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 sha256 去重，保留最早出现的一条。

    只做像素级精确去重：仿真器会重复回传完全相同的 PNG，这一类占据重复样本的绝大多数。
    感知级近似去重（pHash）需要 Pillow，本项目未引入，故不做——宁可少去重，
    也不能凭空声称"已做近似去重"。
    """
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        digest = record.get("sha256") or ""
        if not digest:
            # 没有哈希的样本无法证明唯一性，保守地丢弃并记录原因
            dropped.append({**record, "drop_reason": "MISSING_SHA256"})
            continue
        if digest in seen:
            dropped.append({**record, "drop_reason": "DUPLICATE_SHA256"})
            continue
        seen.add(digest)
        kept.append(record)
    return kept, dropped


def filter_frames(
    records: Iterable[dict[str, Any]],
    min_bytes: int = 1024,
    max_bytes: int = 8 * 1024 * 1024,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """体积过滤：过小的多是残帧/占位图，过大的不吃进数据集（训练时仍会被缩放）。"""
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for record in records:
        size = int(record.get("bytes") or 0)
        if size < min_bytes:
            dropped.append({**record, "drop_reason": f"TOO_SMALL:{size}"})
        elif size > max_bytes:
            dropped.append({**record, "drop_reason": f"TOO_LARGE:{size}"})
        else:
            kept.append(record)
    return kept, dropped


def stratified_sample(
    records: Iterable[dict[str, Any]],
    per_target_limit: int = 0,
    per_device_limit: int = 0,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 target / device 分层限量，桶内等距抽取以覆盖整个时间跨度。

    限量为 0 表示该维度不限。等距而非取前 N：关键帧按时间流入，
    取前 N 会让数据集只反映巡检开头那几分钟。
    """
    ordered = sorted(records, key=lambda item: item.get("captured_at") or "")
    kept = _cap(_cap(ordered, "target", per_target_limit), "device_key", per_device_limit)
    kept_ids = {id(record) for record in kept}
    dropped = [{**record, "drop_reason": "SAMPLED_OUT"} for record in ordered if id(record) not in kept_ids]
    return kept, dropped


def _cap(records: Sequence[dict[str, Any]], key: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return list(records)
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for record in records:
        buckets.setdefault(record.get(key), []).append(record)
    selected: list[dict[str, Any]] = []
    for bucket in buckets.values():
        selected.extend(_evenly_spaced(bucket, limit))
    # 恢复时间序，后续切分依赖顺序
    return sorted(selected, key=lambda item: item.get("captured_at") or "")


def _evenly_spaced(bucket: Sequence[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if len(bucket) <= limit:
        return list(bucket)
    if limit <= 1:
        return [bucket[0]]
    # 首尾都要取到：步长按 (len-1)/(limit-1)，否则只覆盖前段、丢掉最新帧
    step = (len(bucket) - 1) / (limit - 1)
    return [bucket[round(index * step)] for index in range(limit)]


def split_by_time(
    records: Iterable[dict[str, Any]],
    val_ratio: float = 0.2,
) -> dict[str, list[dict[str, Any]]]:
    """按时间切 train/val：后段做验证，模拟"用历史训练、预测未来"。"""
    ordered = sorted(records, key=lambda item: item.get("captured_at") or "")
    if not ordered:
        return {"train": [], "val": []}
    if val_ratio <= 0 or len(ordered) == 1:
        return {"train": ordered, "val": []}
    val_count = max(1, int(round(len(ordered) * min(val_ratio, 0.9))))
    val_count = min(val_count, len(ordered) - 1)  # 训练集至少留 1 张
    return {"train": ordered[:-val_count], "val": ordered[-val_count:]}


def write_yolo_dataset(
    splits: dict[str, list[dict[str, Any]]],
    out_dir: Path | str,
    class_names: Sequence[str],
    preset: str = "",
) -> dict[str, Any]:
    """写出标准 YOLO 目录：images/ labels/ data.yaml。

    **label 文件是空的**——本函数只负责把图摆成 YOLO 能吃的形状，
    真实框由外部标注工具（Label Studio / labelImg）产出后写回同名 .txt。
    空 label 在 YOLO 语义下是"负样本"，不是错误数据。
    """
    out = Path(out_dir)
    manifest: list[dict[str, Any]] = []
    counts: dict[str, int] = {}

    for split, records in splits.items():
        image_dir = out / "images" / split
        label_dir = out / "labels" / split
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        counts[split] = 0
        for record in records:
            source = Path(record["file_path"])
            if not source.is_file():
                # 文件丢了就跳过并留证据，不往数据集里放 0 字节占位
                record["copy_status"] = "MISSING_FILE"
                continue
            stem = f"{record.get('frame_id')}_{str(record.get('sha256') or '')[:8]}"
            target = image_dir / f"{stem}{source.suffix.lower()}"
            shutil.copyfile(source, target)
            # 空 label：负样本，等人工框选后覆盖
            (label_dir / f"{stem}.txt").touch()
            counts[split] += 1
            manifest.append({**record, "yolo_image": str(target.relative_to(out)), "split": split})

    data_yaml = out / "data.yaml"
    data_yaml.write_text(_render_data_yaml(out, class_names), encoding="utf-8")
    # 清单留档：训练报告要能追溯到"这一版数据集用了哪些帧"
    manifest_path = out / "manifest.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for item in manifest:
            handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    return {
        "out": str(out),
        "preset": preset,
        "classes": list(class_names),
        "counts": counts,
        "data_yaml": str(data_yaml),
        "manifest": str(manifest_path),
    }


def _render_data_yaml(out: Path, class_names: Sequence[str]) -> str:
    """手写 YAML：避免为几行配置引入 PyYAML 依赖。"""
    lines = [
        f"path: {out.resolve().as_posix()}",
        "train: images/train",
        "val: images/val",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in enumerate(class_names))
    return "\n".join(lines) + "\n"


def write_jsonl(records: Iterable[dict[str, Any]], path: Path | str) -> str:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return str(target)


def read_jsonl(path: Path | str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise ValueError(f"{path} 第 {lineno} 行不是合法 JSON：{error}") from error
    return records
