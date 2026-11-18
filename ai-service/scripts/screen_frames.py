"""VLM 二分类筛图：从几千张关键帧里挑出"可能值得标注"的那几十张。

用法（在 ai-service 目录下执行）：

    # 1) 先看会处理哪些图，不调模型
    python scripts/screen_frames.py --data ../data/vision/yolo --dry-run

    # 2) 正式筛（产物写到 screen/，不碰 labels/）
    python scripts/screen_frames.py --data ../data/vision/yolo \
        --out ../data/vision/screen --model qwen2.5vl:3b

    # 3) 人工标注时只打开候选清单
    #    labelImg 支持从文件读取待标列表
    labelImg ../data/vision/yolo/images/train ../data/vision/yolo/labels/train \
        ../data/vision/screen/suspects.txt

产物：
- screen/screen.jsonl        每帧一行判定明细（含原始输出，便于复盘误判）
- screen/suspects.txt        判为"有目标"的图片绝对路径，一行一个 → 标注队列
- screen/uncertain.txt       模型说不清的图片，同样要人工看，优先级次于 suspects
- screen/screen.report.json  分布统计 + 判别力自检结论

边界：
- 不写任何 label 文件。筛图只决定"人先看哪张"，不产生真值；
- 调用失败按张记账；全部失败退出码 2，不写半套结果冒充成功；
- 输出目录已存在时必须显式 --overwrite，避免覆盖人工已处理的队列。
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

from app.vision.ollama import call_vision  # noqa: E402
from app.vision.screening import (  # noqa: E402
    build_screen_prompt,
    parse_screen_result,
    summarize,
)
from app.vision.weak_label import load_class_names  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "vision" / "yolo"
DEFAULT_MODEL = os.getenv("LLM_VISION_MODEL", "qwen2.5vl:3b")
DEFAULT_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:11434")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
# 二分类输出很短，给 128 tokens 足够；给太多反而给模型编造理由的空间
SCREEN_NUM_PREDICT = 128


def collect_images(data_dir: Path, splits: list[str]) -> list[tuple[str, Path]]:
    """按 split 收集图片，split 顺序固定便于复现。"""
    images: list[tuple[str, Path]] = []
    for split in splits:
        directory = data_dir / "images" / split
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                images.append((split, path))
    return images


def main() -> int:
    parser = argparse.ArgumentParser(description="VLM 二分类筛图（挑出疑似含目标的帧）")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="YOLO 数据集目录（含 data.yaml）")
    parser.add_argument("--out", default="", help="输出目录，默认 <data>/screen")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--splits", default="train,val")
    parser.add_argument("--limit", type=int, default=0, help="最多处理多少张，0 表示全部")
    parser.add_argument("--timeout", type=float, default=180.0)
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

    out_dir = Path(args.out).resolve() if args.out else data_dir / "screen"
    report_path = out_dir / "screen.report.json"

    print(f"数据集 : {data_dir}")
    print(f"类别   : {', '.join(class_names)}")
    print(f"图片   : {len(images)} 张（splits={splits}）")
    print(f"模型   : {args.model} @ {args.base_url}")
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

    prompt = build_screen_prompt(class_names)
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    decisions: list[str] = []
    suspects: list[str] = []
    uncertain_images: list[str] = []
    failures = 0
    started = time.perf_counter()

    for index, (split, path) in enumerate(images, start=1):
        record: dict = {"split": split, "image": path.name, "path": str(path)}
        try:
            image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            raw = call_vision(
                args.base_url, args.model, prompt, image_b64, args.timeout,
                num_predict=SCREEN_NUM_PREDICT,
            )
            verdict = parse_screen_result(raw, class_names)
            record.update(
                {
                    "decision": verdict.decision,
                    "labels": list(verdict.labels),
                    "confidence": verdict.confidence,
                    "reason": verdict.reason,
                    "notes": list(verdict.notes),
                    "raw_response": raw[:600],
                }
            )
            decisions.append(verdict.decision)
            if verdict.decision == "yes":
                suspects.append(str(path))
            elif verdict.decision == "uncertain":
                uncertain_images.append(str(path))
            print(
                f"  [{index}/{len(images)}] {split}/{path.name} → {verdict.decision}"
                + (f" {','.join(verdict.labels)}" if verdict.labels else "")
            )
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as error:
            failures += 1
            record["decision"] = "failed"
            record["error"] = f"{type(error).__name__}: {error}"
            print(f"  [{index}/{len(images)}] {split}/{path.name} → 失败：{error}")
        records.append(record)

    elapsed = round(time.perf_counter() - started, 2)
    summary = summarize(decisions, failed=failures)

    jsonl_path = out_dir / "screen.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    suspects_path = out_dir / "suspects.txt"
    suspects_path.write_text(
        "\n".join(suspects) + ("\n" if suspects else ""), encoding="utf-8"
    )
    uncertain_path = out_dir / "uncertain.txt"
    uncertain_path.write_text(
        "\n".join(uncertain_images) + ("\n" if uncertain_images else ""), encoding="utf-8"
    )

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "base_url": args.base_url,
        "classes": list(class_names),
        "summary": {**summary, "elapsed_sec": elapsed},
        "note": "筛图只决定人工先看哪张，不产生任何训练真值；uncertain 必须人工复核",
        # 报告只放判定摘要，原始输出留在 screen.jsonl：
        # 几千帧的 raw_response 塞进 JSON 报告会让文件大到打不开
        "frames": [
            {key: value for key, value in record.items() if key != "raw_response"}
            for record in records
        ],
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[OK] yes {summary['yes']} / no {summary['no']} / uncertain {summary['uncertain']} / "
        f"失败 {failures}，耗时 {elapsed}s"
    )
    print(f"[OK] 标注队列：{suspects_path}")
    print(f"[OK] 待复核：{uncertain_path}")
    print(f"[OK] 报告：{report_path}")
    if summary["low_discrimination"]:
        print(f"[WARN] {summary['warning']}")
    if failures == len(images):
        print("[FAIL] 全部图片调用失败，检查 Ollama 与视觉模型是否可用")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
