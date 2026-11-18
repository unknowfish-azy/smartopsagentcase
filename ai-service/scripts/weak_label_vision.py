"""弱标注候选：先粗框一遍，人工再改成精标注。

两个出框引擎，产物格式完全一致，可互换：

    --engine grounding  GroundingDINO 开放词表检测（推荐，默认）
    --engine vlm        qwen2.5vl:3b 走 Ollama（保留用于对照与复盘）

为什么默认换成 GroundingDINO：VLM 在 30 帧实测里既出不准框（坐标跨图复读），
也做不了筛图（异常帧召回 12.5%），根因是小目标细节在视觉编码后丢失；
专职检测器不吃这个亏。

用法（在 ai-service 目录下执行）：

    # 1) 先看清单，不加载模型
    python scripts/weak_label_vision.py --data ../data/vision/yolo --dry-run

    # 2) 生成候选框（写到 weak/labels/，不碰 labels/）
    python scripts/weak_label_vision.py --data ../data/vision/yolo \
        --out ../data/vision/weak --engine grounding

    # 3) 人工复核后，把改好的 txt 覆盖回 labels/train|val/

产物：
- weak/labels/<split>/<图片名>.txt   YOLO 行，**只是候选**
- weak/weak.report.json              每张图的接受/拒绝明细 + 引擎参数，用于复盘

边界：
- 原 labels/ 一律不动。空 label 代表"负样本"，被弱标注覆盖会污染真值语义；
- 单图失败按张记账，全部失败时退出码 2，不写半套结果冒充成功；
- 输出目录已存在时必须显式 --overwrite，避免覆盖人工改过的候选。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.grounding import DEFAULT_MODEL as DEFAULT_DETECTOR
from app.vision.grounding import GroundingDetector
from app.vision.ollama import call_vision  # noqa: E402
from app.vision.weak_label import (  # noqa: E402
    CandidateBox,
    build_prompt,
    degenerate_signatures,
    format_yolo_line,
    load_class_names,
    parse_candidates,
)

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "vision" / "yolo"
DEFAULT_MODEL = os.getenv("LLM_VISION_MODEL", "qwen2.5vl:3b")
DEFAULT_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def collect_images(data_dir: Path, splits: list[str]) -> list[tuple[str, Path]]:
    """按 split 收集待标注图片，split 顺序固定便于复现。"""
    images: list[tuple[str, Path]] = []
    for split in splits:
        directory = data_dir / "images" / split
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                images.append((split, path))
    return images


def run_grounding(
    detector: GroundingDetector,
    path: Path,
    class_names: list[str],
    box_threshold: float,
    text_threshold: float,
) -> tuple[list[CandidateBox], list[str], str | None]:
    """检测器引擎：直接从像素出框，没有"模型原始文本"这一层。"""
    from PIL import Image

    with Image.open(path) as image:
        boxes, rejected = detector.detect(
            image.convert("RGB"), class_names, box_threshold, text_threshold
        )
    return boxes, rejected, None


def run_vlm(
    args: argparse.Namespace,
    path: Path,
    prompt: str,
    class_names: list[str],
) -> tuple[list[CandidateBox], list[str], str | None]:
    """VLM 引擎：走 Ollama，输出需要解析与拒收。"""
    image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    raw = call_vision(args.base_url, args.model, prompt, image_b64, args.timeout)
    boxes, rejected = parse_candidates(raw, class_names)
    return boxes, rejected, raw


def main() -> int:
    parser = argparse.ArgumentParser(description="弱标注候选生成（检测器 / VLM 双引擎）")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="YOLO 数据集目录（含 data.yaml）")
    parser.add_argument("--out", default="", help="候选输出目录，默认 <data>/weak")
    parser.add_argument(
        "--engine", choices=("grounding", "vlm"), default="grounding",
        help="出框引擎：grounding=GroundingDINO（默认），vlm=Ollama 视觉模型",
    )
    parser.add_argument("--detector-model", default=DEFAULT_DETECTOR, help="GroundingDINO 权重")
    parser.add_argument("--box-threshold", type=float, default=0.30, help="检测框置信度阈值")
    parser.add_argument("--text-threshold", type=float, default=0.25, help="文本匹配阈值")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="VLM 引擎使用的模型名")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--splits", default="train,val")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少张，0 表示全部")
    parser.add_argument("--timeout", type=float, default=180.0, help="VLM 单张超时（秒）")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data).resolve()
    data_yaml = data_dir / "data.yaml"
    if not data_yaml.is_file():
        print(f"[FAIL] 找不到 data.yaml：{data_yaml}")
        return 1

    class_names = load_class_names(data_yaml)
    if not class_names:
        print(f"[FAIL] data.yaml 里没有解析出类别：{data_yaml}")
        return 1

    splits = [item.strip() for item in args.splits.split(",") if item.strip()]
    images = collect_images(data_dir, splits)
    if args.limit > 0:
        images = images[: args.limit]
    if not images:
        print(f"[FAIL] {data_dir} 下没有可处理的图片（splits={splits}）")
        return 1

    out_dir = Path(args.out).resolve() if args.out else data_dir / "weak"
    report_path = out_dir / "weak.report.json"

    print(f"数据集 : {data_dir}")
    print(f"类别   : {', '.join(class_names)}")
    print(f"图片   : {len(images)} 张（splits={splits}）")
    if args.engine == "grounding":
        print(f"引擎   : grounding（{args.detector_model}，box>{args.box_threshold}）")
    else:
        print(f"引擎   : vlm（{args.model} @ {args.base_url}）")
    print(f"输出   : {out_dir}")

    if args.dry_run:
        for split, path in images[:10]:
            print(f"  [dry-run] {split}/{path.name}")
        if len(images) > 10:
            print(f"  [dry-run] ... 其余 {len(images) - 10} 张")
        print("[OK] dry-run 结束，未调用模型")
        return 0

    if report_path.exists() and not args.overwrite:
        print(f"[FAIL] {report_path} 已存在，确认要覆盖请加 --overwrite")
        return 1

    prompt = build_prompt(class_names)
    detector = GroundingDetector(args.detector_model) if args.engine == "grounding" else None
    out_dir.mkdir(parents=True, exist_ok=True)
    details: list[dict] = []
    candidates: dict[str, tuple[str, Path, list[CandidateBox]]] = {}
    written: dict[str, Path] = {}
    failures = 0
    with_boxes = 0
    total_boxes = 0
    started = time.perf_counter()

    for index, (split, path) in enumerate(images, start=1):
        key = f"{split}/{path.name}"
        record: dict = {"split": split, "image": path.name, "accepted": 0, "rejected": []}
        try:
            if detector is not None:
                boxes, rejected, raw = run_grounding(
                    detector, path, class_names, args.box_threshold, args.text_threshold
                )
            else:
                boxes, rejected, raw = run_vlm(args, path, prompt, class_names)
            if raw is not None:
                record["raw_response"] = raw[:1200]
            record["rejected"] = rejected
            if boxes:
                label_path = out_dir / "labels" / split / f"{path.stem}.txt"
                label_path.parent.mkdir(parents=True, exist_ok=True)
                label_path.write_text(
                    "\n".join(format_yolo_line(box, class_names) for box in boxes) + "\n",
                    encoding="utf-8",
                )
                candidates[key] = (split, path, boxes)
                written[key] = label_path
                with_boxes += 1
                total_boxes += len(boxes)
            record["accepted"] = len(boxes)
            print(
                f"  [{index}/{len(images)}] {key} → {len(boxes)} 框"
                + (f"（拒绝 {len(rejected)}）" if rejected else "")
            )
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as error:
            failures += 1
            record["error"] = f"{type(error).__name__}: {error}"
            print(f"  [{index}/{len(images)}] {key} → 失败：{error}")
        details.append(record)

    # 判伪：跨图逐位相同的框是模型复读模板，不进候选、留证据
    suspects = degenerate_signatures(
        {key: boxes for key, (_, _, boxes) in candidates.items()}
    )
    degenerate_images = 0
    if suspects:
        for key, (split, path, boxes) in candidates.items():
            kept = [
                box
                for box in boxes
                if (box.label, box.cx, box.cy, box.w, box.h) not in suspects
            ]
            if len(kept) == len(boxes):
                continue
            degenerate_images += 1
            total_boxes -= len(boxes) - len(kept)
            with_boxes -= 1 if not kept else 0
            if kept:
                written[key].write_text(
                    "\n".join(format_yolo_line(box, class_names) for box in kept) + "\n",
                    encoding="utf-8",
                )
            else:
                written[key].unlink(missing_ok=True)
            for detail in details:
                if detail["split"] == split and detail["image"] == path.name:
                    detail["accepted"] = len(kept)
                    detail["suspect"] = True
                    detail["rejected"] = list(detail.get("rejected") or []) + [
                        "跨图坐标逐位相同，判定为模型复读模板"
                    ]

    elapsed = round(time.perf_counter() - started, 2)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": args.engine,
        "model": args.detector_model if args.engine == "grounding" else args.model,
        "base_url": args.base_url if args.engine == "vlm" else None,
        "thresholds": {
            "box": args.box_threshold if args.engine == "grounding" else None,
            "text": args.text_threshold if args.engine == "grounding" else None,
        },
        "classes": list(class_names),
        "summary": {
            "images": len(images),
            "images_with_candidates": with_boxes,
            "images_empty": len(images) - with_boxes - failures,
            "images_failed": failures,
            "total_candidates": total_boxes,
            "images_degenerate_dropped": degenerate_images,
            "elapsed_sec": elapsed,
        },
        "note": "候选框仅供人工复核，未经复核不得直接作为训练真值",
        "images": details,
    }
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(
        f"[OK] {with_boxes}/{len(images)} 张产出候选，共 {total_boxes} 个框，"
        f"失败 {failures} 张，耗时 {elapsed}s"
    )
    print(f"[OK] 报告：{report_path}")
    if failures == len(images):
        print("[FAIL] 全部图片调用失败，检查 Ollama 与视觉模型是否可用")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
