"""把 Open Images 的 Person 标注 + 图片清单构造成 YOLO 数据集。

为什么不用 FiftyOne：官方图片清单 CSV 本身就带 `OriginalURL / License / Rotation`，
复用本仓的 https 下载器即可，不必新增一个重依赖。

    # 先拉清单（白名单内，已核验）
    python scripts/fetch_public_vision_data.py --fetch openimages_v7_validation_image_urls

    # 看会选多少张、跳过多少，不下图片
    python scripts/build_openimages_person_subset.py --dry-run

    # 真实抓取 200 张（逐图记录 sha256 与许可证）
    python scripts/build_openimages_person_subset.py --limit 200

    # 把 Person + Man/Woman/Boy/Girl 合并成 person（按 IoU 去重）
    python scripts/build_openimages_person_subset.py --limit 200 --include-gendered

产物（默认 data/vision/openimages_person_preview）：
    images/{train,val}/<ImageID>.jpg
    labels/{train,val}/<ImageID>.txt   # YOLO: "0 cx cy w h"（归一化）
    data.yaml                          # names: {0: person}
    manifest.jsonl                     # 每图 url / license / sha256 / 框数 / 状态
    SOURCE.json                        # 上游数据集、过滤参数与计数

口径：
1. 默认只用 `Person`（/m/01g317）且 `Confidence=1`，排除 IsGroupOf / IsDepiction；
2. 图片许可证默认只放行 CC BY 2.0/4.0、CC0、PDM；逐图记录，不用"整包一个许可证"糊过去；
3. 默认跳过 Rotation 非 0 的图片（标注坐标与旋转后的显示方向可能对不上）；
4. 默认只接受 https 原图 URL；下载失败/内容不是图片都记账，不静默丢。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:  # pytest 从 ai-service 根目录导入
    from scripts.fetch_public_vision_data import FetchError, download as _download
except ImportError:  # 直接 python scripts/build_openimages_person_subset.py
    from fetch_public_vision_data import FetchError, download as _download

SCHEMA_VERSION = "smartops.openimages_subset.v1"
CLASS_MIDS = {
    "Person": "/m/01g317",
    "Man": "/m/04yx4",
    "Woman": "/m/03bt1vf",
    "Boy": "/m/01bl7v",
    "Girl": "/m/05r655",
}
DEFAULT_ALLOWED_LICENSES = (
    "https://creativecommons.org/licenses/by/2.0/",
    "https://creativecommons.org/licenses/by/4.0/",
    "https://creativecommons.org/publicdomain/zero/1.0/",
    "https://creativecommons.org/publicdomain/mark/1.0/",
)
AI_SERVICE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ANNOTATIONS = (
    AI_SERVICE_ROOT
    / "data/vision/public/openimages_v7_validation_bbox_annotations/validation-annotations-bbox.csv"
)
DEFAULT_IMAGE_LIST = (
    AI_SERVICE_ROOT
    / "data/vision/public/openimages_v7_validation_image_urls/validation-images-with-rotation.csv"
)
DEFAULT_OUT = AI_SERVICE_ROOT / "data/vision/openimages_person_preview"


class SubsetError(RuntimeError):
    """输入不合法或无法继续构造数据集。"""


@dataclass(frozen=True)
class Box:
    label: str
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)


# ---------------------------------------------------------------------------
# 读取与过滤
# ---------------------------------------------------------------------------


def load_annotations(
    path: Path | str,
    classes: Iterable[str] = ("Person",),
    *,
    verify_only: bool = True,
    include_group_of: bool = False,
    include_depiction: bool = False,
) -> tuple[dict[str, list[Box]], Counter]:
    """按类过滤标注，返回 {ImageID: [Box]} 与丢弃原因计数。"""
    wanted = {}
    for name in classes:
        if name not in CLASS_MIDS:
            raise SubsetError(f"不支持的类：{name}，可选 {sorted(CLASS_MIDS)}")
        wanted[CLASS_MIDS[name]] = name

    source = Path(path)
    if not source.is_file():
        raise SubsetError(f"标注文件不存在：{source}")

    images: dict[str, list[Box]] = {}
    skipped: Counter = Counter()
    with source.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            name = wanted.get(row.get("LabelName", ""))
            if not name:
                continue
            if verify_only and str(row.get("Confidence", "")).strip() not in ("1", "1.0"):
                skipped["unverified"] += 1
                continue
            if not include_group_of and str(row.get("IsGroupOf", "0")).strip() == "1":
                skipped["group_of"] += 1
                continue
            if not include_depiction and str(row.get("IsDepiction", "0")).strip() == "1":
                skipped["depiction"] += 1
                continue
            try:
                x1, x2 = float(row["XMin"]), float(row["XMax"])
                y1, y2 = float(row["YMin"]), float(row["YMax"])
            except (KeyError, TypeError, ValueError):
                skipped["bad_coords"] += 1
                continue
            x1, x2 = sorted((min(max(x1, 0.0), 1.0), min(max(x2, 0.0), 1.0)))
            y1, y2 = sorted((min(max(y1, 0.0), 1.0), min(max(y2, 0.0), 1.0)))
            if x2 - x1 <= 0.0 or y2 - y1 <= 0.0:
                skipped["degenerate"] += 1
                continue
            images.setdefault(row["ImageID"], []).append(Box(name, x1, y1, x2, y2))
    return images, skipped


def dedupe_boxes(boxes: list[Box], iou_threshold: float = 0.5) -> list[Box]:
    """同一实例被 Person 与性别类重复标注时，按面积降序做贪心去重。

    同面积时优先保留通用类 `Person`，避免子集里混入 `Man/Woman` 的标签来源。
    """
    ordered = sorted(
        boxes,
        key=lambda box: (0 if box.label == "Person" else 1, -box.area, box.x1, box.y1),
    )
    kept: list[Box] = []
    for box in ordered:
        if all(_iou(box, other) < iou_threshold for other in kept):
            kept.append(box)
    return kept


def _iou(left: Box, right: Box) -> float:
    x1 = max(left.x1, right.x1)
    y1 = max(left.y1, right.y1)
    x2 = min(left.x2, right.x2)
    y2 = min(left.y2, right.y2)
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = left.area + right.area - inter
    return inter / union if union > 0 else 0.0


def load_image_meta(path: Path | str) -> dict[str, dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise SubsetError(f"图片清单不存在：{source}（先跑 fetch_public_vision_data.py）")
    meta: dict[str, dict[str, Any]] = {}
    with source.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            image_id = row.get("ImageID")
            if not image_id:
                continue
            meta[image_id] = {
                "url": (row.get("OriginalURL") or "").strip(),
                "license": (row.get("License") or "").strip(),
                "md5": (row.get("OriginalMD5") or "").strip(),
                "size": _to_int(row.get("OriginalSize")),
                "rotation": (row.get("Rotation") or "").strip(),
            }
    return meta


def select_images(
    annotations: dict[str, list[Box]],
    meta: dict[str, dict[str, Any]],
    *,
    limit: int,
    allowed_licenses: Iterable[str] = DEFAULT_ALLOWED_LICENSES,
    allow_rotation: bool = False,
) -> tuple[list[tuple[str, list[Box], dict[str, Any]]], Counter]:
    if limit <= 0:
        raise SubsetError("limit 必须大于 0")
    allowed = set(allowed_licenses)
    selected: list[tuple[str, list[Box], dict[str, Any]]] = []
    skipped: Counter = Counter()

    for image_id in sorted(annotations):
        boxes = annotations[image_id]
        if not boxes:
            continue
        info = meta.get(image_id)
        if not info:
            skipped["no_meta"] += 1
            continue
        if not info["url"].startswith("https://"):
            skipped["non_https"] += 1
            continue
        if info["license"] not in allowed:
            skipped["license_not_allowed"] += 1
            continue
        if not allow_rotation and info["rotation"] not in ("", "0", "0.0", "None"):
            skipped["rotated"] += 1
            continue
        selected.append((image_id, boxes, info))
        if len(selected) >= limit:
            break
    return selected, skipped


# ---------------------------------------------------------------------------
# 落盘
# ---------------------------------------------------------------------------


def to_yolo_lines(boxes: Iterable[Box]) -> list[str]:
    lines: list[str] = []
    for box in boxes:
        width = box.x2 - box.x1
        height = box.y2 - box.y1
        lines.append(
            f"0 {(box.x1 + box.x2) / 2:.6f} {(box.y1 + box.y2) / 2:.6f} "
            f"{width:.6f} {height:.6f}"
        )
    return lines


def split_of(image_id: str, val_ratio: float) -> str:
    if val_ratio <= 0:
        return "train"
    bucket = int(hashlib.sha1(image_id.encode("utf-8")).hexdigest()[:8], 16) % 1000
    return "val" if bucket < val_ratio * 1000 else "train"


def _fetch_one(
    image_id: str,
    boxes: list[Box],
    info: dict[str, Any],
    *,
    out: Path,
    val_ratio: float,
    timeout: float,
    max_bytes: int,
    downloader: Any,
) -> dict[str, Any]:
    """下载并落盘单张图；失败只返回 FAILED 记录，不抛给主流程。"""
    split = split_of(image_id, val_ratio)
    image_path = out / "images" / split / f"{image_id}.jpg"
    label_path = out / "labels" / split / f"{image_id}.txt"

    record: dict[str, Any] = {
        "image_id": image_id,
        "split": split,
        "url": info["url"],
        "license": info["license"],
        "upstream_md5": info["md5"],
        "rotation": info["rotation"],
        "boxes": len(boxes),
    }
    try:
        if image_path.is_file() and is_image_bytes(image_path):
            record.update(status="REUSED", sha256=_sha256(image_path),
                          bytes=image_path.stat().st_size)
        else:
            image_path.unlink(missing_ok=True)
            sha256, size = downloader(
                info["url"], image_path, timeout=timeout, max_bytes=max_bytes
            )
            if not is_image_bytes(image_path):
                image_path.unlink(missing_ok=True)
                raise FetchError("下载内容不是图片（可能是失效链接的错误页）")
            record.update(status="DOWNLOADED", sha256=sha256, bytes=size)
    except Exception as error:  # 单图失败继续，逐条记账
        image_path.unlink(missing_ok=True)
        record.update(status="FAILED", error=f"{type(error).__name__}: {error}")

    if record["status"] != "FAILED":
        label_path.write_text("\n".join(to_yolo_lines(boxes)) + "\n", encoding="utf-8")
    return record


def is_image_bytes(path: Path) -> bool:
    with path.open("rb") as handle:
        head = handle.read(8)
    return head.startswith(b"\xff\xd8") or head.startswith(b"\x89PNG") or head[:4] == b"RIFF"


def build(
    annotations_path: Path | str,
    image_list_path: Path | str,
    out_dir: Path | str = DEFAULT_OUT,
    *,
    classes: Iterable[str] = ("Person",),
    limit: int = 200,
    val_ratio: float = 0.2,
    allowed_licenses: Iterable[str] = DEFAULT_ALLOWED_LICENSES,
    allow_rotation: bool = False,
    timeout: float = 15.0,
    max_bytes: int = 20 * 1024 * 1024,
    workers: int = 8,
    downloader: Any = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    classes = tuple(classes)
    downloader = downloader or _download
    annotations, annotation_skipped = load_annotations(annotations_path, classes)
    if len(classes) > 1:
        annotations = {key: dedupe_boxes(value) for key, value in annotations.items()}
    meta = load_image_meta(image_list_path)
    selected, selection_skipped = select_images(
        annotations,
        meta,
        limit=limit,
        allowed_licenses=allowed_licenses,
        allow_rotation=allow_rotation,
    )

    summary: dict[str, Any] = {
        "selected": len(selected),
        "images_with_boxes": len(annotations),
        "boxes": sum(len(boxes) for _, boxes, _ in selected),
        "annotation_skipped": dict(annotation_skipped),
        "selection_skipped": dict(selection_skipped),
        "classes": list(classes),
        "limit": limit,
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    out = Path(out_dir)
    for split in ("train", "val"):
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [
            pool.submit(
                _fetch_one,
                image_id,
                boxes,
                info,
                out=out,
                val_ratio=val_ratio,
                timeout=timeout,
                max_bytes=max_bytes,
                downloader=downloader,
            )
            for image_id, boxes, info in selected
        ]
        records = [future.result() for future in futures]

    downloaded = sum(1 for record in records if record["status"] == "DOWNLOADED")
    reused = sum(1 for record in records if record["status"] == "REUSED")
    failed = sum(1 for record in records if record["status"] == "FAILED")

    _write_jsonl(out / "manifest.jsonl", records)
    (out / "data.yaml").write_text(_render_data_yaml(out), encoding="utf-8")
    source = {
        "schema_version": SCHEMA_VERSION,
        "created_at": _now(),
        "annotations": {
            "path": str(Path(annotations_path).resolve()),
            "sha256": _sha256(Path(annotations_path)),
        },
        "image_list": {
            "path": str(Path(image_list_path).resolve()),
            "sha256": _sha256(Path(image_list_path)),
        },
        "classes": list(classes),
        "allowed_licenses": sorted(set(allowed_licenses)),
        "allow_rotation": allow_rotation,
        "val_ratio": val_ratio,
        "counts": {
            "selected": len(selected),
            "downloaded": downloaded,
            "reused": reused,
            "failed": failed,
            "boxes": summary["boxes"],
        },
        "skipped": {
            "annotation": dict(annotation_skipped),
            "selection": dict(selection_skipped),
        },
        "notes": "派生数据集。上游为 Open Images V7（标注 CC BY 4.0）；单图许可证见 manifest.jsonl。",
    }
    (out / "SOURCE.json").write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    summary.update(downloaded=downloaded, reused=reused, failed=failed, out=str(out))
    return summary


def _render_data_yaml(out: Path) -> str:
    return (
        f"path: {out.resolve().as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "names:\n"
        "  0: person\n"
    )


def _write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Open Images Person 子集 → YOLO 数据集")
    parser.add_argument("--annotations", default=str(DEFAULT_ANNOTATIONS))
    parser.add_argument("--image-list", default=str(DEFAULT_IMAGE_LIST))
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--include-gendered", action="store_true",
                        help="把 Man/Woman/Boy/Girl 也映射成 person（按 IoU 去重）")
    parser.add_argument("--allow-rotation", action="store_true", help="允许 Rotation 非 0 的图片")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--max-bytes", type=int, default=20 * 1024 * 1024)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    classes = ["Person", "Man", "Woman", "Boy", "Girl"] if args.include_gendered else ["Person"]
    try:
        summary = build(
            args.annotations,
            args.image_list,
            args.out,
            classes=classes,
            limit=args.limit,
            val_ratio=args.val_ratio,
            allow_rotation=args.allow_rotation,
            timeout=args.timeout,
            workers=args.workers,
            max_bytes=args.max_bytes,
            dry_run=args.dry_run,
        )
    except SubsetError as error:
        print(f"[subset] {error}", file=sys.stderr)
        return 2

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not args.dry_run and summary.get("failed"):
        print(f"[subset] {summary['failed']} 张图片下载失败，详见 manifest.jsonl", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
