"""视觉数据集导出：robot_frame → 蒸馏清单 → YOLO 目录。

用法（在 ai-service 目录下执行）：

    # 1) 从 DB 取关键帧登记，生成原始清单
    python scripts/export_vision_dataset.py captures --out ../data/vision/raw.jsonl --since 2026-11-01

    # 2) 蒸馏：去重 + 体积过滤 + 按 target/device 分层限量
    python scripts/export_vision_dataset.py distill --input ../data/vision/raw.jsonl \
        --out ../data/vision/distilled.jsonl --per-target 400 --per-device 800

    # 3) 落成 YOLO 数据集（images/ labels/ data.yaml）
    python scripts/export_vision_dataset.py yolo --input ../data/vision/distilled.jsonl \
        --out ../data/vision/yolo --classes coco_subset --val-ratio 0.2

    # 一条命令跑完
    python scripts/export_vision_dataset.py all --out ../data/vision --classes patrol_anomaly

说明：
- 图像根目录默认 ../data/robot-frames（与后端 smartops.robot.frame-archive.dir 一致），
  用 --frames-root 覆盖；
- 导出的 label 是**空文件**（负样本），真实框要用 labelImg / Label Studio 标注后写回；
- 类别预设见 app/vision/classes.py，也可用 --classes 指向自建 JSON。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.classes import resolve_classes  # noqa: E402
from app.vision.dataset import (  # noqa: E402
    dedupe,
    filter_frames,
    normalize_frame_row,
    read_jsonl,
    split_by_time,
    stratified_sample,
    write_jsonl,
    write_yolo_dataset,
)

FRAME_SQL = """
SELECT id AS frame_id, device_key, target, file_path, sha256, bytes,
       width, height, quality, captured_at, simulated
FROM robot_frame
WHERE (%(since)s IS NULL OR captured_at >= %(since)s)
ORDER BY captured_at
LIMIT %(limit)s
"""


def _db_config() -> dict[str, Any]:
    """数据库连接：优先 SMARTOPS_DB_*，回退后端沿用的 MYSQL_*。"""
    return {
        "host": os.getenv("SMARTOPS_DB_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("SMARTOPS_DB_PORT") or os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("SMARTOPS_DB_USER") or os.getenv("MYSQL_USERNAME", "root"),
        "password": os.getenv("SMARTOPS_DB_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("SMARTOPS_DB_NAME") or os.getenv("MYSQL_DATABASE", "smartops"),
    }


def _fetch_frames(since: str | None, limit: int) -> list[dict[str, Any]]:
    import pymysql

    connection = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **_db_config())
    try:
        with connection.cursor() as cursor:
            cursor.execute(FRAME_SQL, {"since": since, "limit": limit})
            return list(cursor.fetchall())
    finally:
        connection.close()


def _mark_distilled(frame_ids: list[int]) -> int:
    """回写 robot_frame.distilled_at，避免同一批帧被反复当作新数据。"""
    if not frame_ids:
        return 0
    import pymysql

    connection = pymysql.connect(**_db_config())
    try:
        with connection.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(frame_ids))
            return cursor.execute(
                f"UPDATE robot_frame SET distilled_at=NOW() WHERE id IN ({placeholders})",
                frame_ids,
            )
    finally:
        connection.close()


def cmd_captures(args: argparse.Namespace) -> None:
    rows = _fetch_frames(args.since, args.limit)
    records = [normalize_frame_row(row, args.frames_root) for row in rows]
    path = write_jsonl(records, args.out)
    print(f"关键帧登记 {len(records)} 条 → {path}")
    if not records:
        print("提示：robot_frame 为空。先启动后端并让机器人回传关键帧，或检查 frame-archive.enabled")


def cmd_distill(args: argparse.Namespace) -> None:
    raw = read_jsonl(args.input)
    deduped, duplicates = dedupe(raw)
    filtered, filtered_out = filter_frames(deduped, args.min_bytes, args.max_bytes)
    sampled, sampled_out = stratified_sample(filtered, args.per_target, args.per_device)

    report = {
        "input": str(args.input),
        "total": len(raw),
        "kept": len(sampled),
        "duplicates_dropped": len(duplicates),
        "size_dropped": len(filtered_out),
        "sample_dropped": len(sampled_out),
        "per_target_limit": args.per_target,
        "per_device_limit": args.per_device,
        "min_bytes": args.min_bytes,
        "max_bytes": args.max_bytes,
    }
    path = write_jsonl(sampled, args.out)
    report_path = Path(args.out).with_suffix(".report.json")
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"蒸馏完成：{len(raw)} → {len(sampled)} 条"
        f"（重复 {len(duplicates)}、体积剔除 {len(filtered_out)}、分层限量 {len(sampled_out)}）"
    )
    print(f"清单 {path}")
    print(f"报告 {report_path}")

    if args.mark_db:
        frame_ids = [int(item["frame_id"]) for item in sampled if item.get("frame_id")]
        try:
            updated = _mark_distilled(frame_ids)
            print(f"已回写 distilled_at：{updated} 行")
        except Exception as error:  # noqa: BLE001 - DB 不可用不应阻断离线蒸馏
            print(f"跳过 distilled_at 回写（DB 不可用：{error}）")


def cmd_yolo(args: argparse.Namespace) -> None:
    preset, classes = resolve_classes(args.classes)
    records = read_jsonl(args.input)
    splits = split_by_time(records, args.val_ratio)
    result = write_yolo_dataset(splits, args.out, classes, preset=preset)
    print(
        f"YOLO 数据集已写出：{result['out']}"
        f"（train {result['counts'].get('train', 0)} / val {result['counts'].get('val', 0)}，"
        f"类别预设 {preset}：{', '.join(classes)}）"
    )
    print(f"data.yaml {result['data_yaml']}")
    print("注意：label 为空文件（负样本），待标框后才有监督信号；标注可用 labelImg / Label Studio")
    missing = [item for item in records if item.get("copy_status") == "MISSING_FILE"]
    if missing:
        print(f"警告：{len(missing)} 张图文件缺失已跳过（先检查 --frames-root 是否指向归档目录）")


def cmd_all(args: argparse.Namespace) -> None:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    raw_path = out / "raw.jsonl"
    distilled_path = out / "distilled.jsonl"
    cmd_captures(argparse.Namespace(
        out=str(raw_path), since=args.since, limit=args.limit,
        frames_root=args.frames_root))
    cmd_distill(argparse.Namespace(
        input=str(raw_path), out=str(distilled_path),
        min_bytes=args.min_bytes, max_bytes=args.max_bytes,
        per_target=args.per_target, per_device=args.per_device, mark_db=args.mark_db))
    cmd_yolo(argparse.Namespace(
        input=str(distilled_path), out=str(out / "yolo"),
        classes=args.classes, val_ratio=args.val_ratio))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="视觉数据集导出（robot_frame → 蒸馏 → YOLO）")
    sub = parser.add_subparsers(dest="command", required=True)

    common_frames = dict(default="../data/robot-frames", help="关键帧归档根目录")

    captures = sub.add_parser("captures", help="从 DB 取关键帧登记 → 原始清单")
    captures.add_argument("--out", required=True)
    captures.add_argument("--since", default=None, help="只取该时间之后的帧（YYYY-MM-DD）")
    captures.add_argument("--limit", type=int, default=50000)
    captures.add_argument("--frames-root", default=common_frames["default"], help=common_frames["help"])
    captures.set_defaults(func=cmd_captures)

    distill = sub.add_parser("distill", help="去重 + 体积过滤 + 分层限量")
    distill.add_argument("--input", required=True)
    distill.add_argument("--out", required=True)
    distill.add_argument("--min-bytes", type=int, default=1024)
    distill.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    distill.add_argument("--per-target", type=int, default=0, help="每个巡检目标最多保留多少张（0=不限）")
    distill.add_argument("--per-device", type=int, default=0, help="每台设备最多保留多少张（0=不限）")
    distill.add_argument("--no-mark-db", dest="mark_db", action="store_false", help="不回写 distilled_at")
    distill.set_defaults(mark_db=True, func=cmd_distill)

    yolo = sub.add_parser("yolo", help="写出 YOLO 目录与 data.yaml")
    yolo.add_argument("--input", required=True)
    yolo.add_argument("--out", required=True)
    yolo.add_argument("--classes", default="coco_subset", help="预设名或 JSON 文件路径")
    yolo.add_argument("--val-ratio", type=float, default=0.2)
    yolo.set_defaults(func=cmd_yolo)

    all_cmd = sub.add_parser("all", help="captures + distill + yolo 一条龙")
    all_cmd.add_argument("--out", required=True, help="输出根目录，例如 ../data/vision")
    all_cmd.add_argument("--since", default=None)
    all_cmd.add_argument("--limit", type=int, default=50000)
    all_cmd.add_argument("--frames-root", default=common_frames["default"])
    all_cmd.add_argument("--min-bytes", type=int, default=1024)
    all_cmd.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    all_cmd.add_argument("--per-target", type=int, default=0)
    all_cmd.add_argument("--per-device", type=int, default=0)
    all_cmd.add_argument("--classes", default="coco_subset")
    all_cmd.add_argument("--val-ratio", type=float, default=0.2)
    all_cmd.add_argument("--no-mark-db", dest="mark_db", action="store_false")
    all_cmd.set_defaults(mark_db=True, func=cmd_all)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
