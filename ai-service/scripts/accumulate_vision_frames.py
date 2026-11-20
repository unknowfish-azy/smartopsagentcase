"""增量积累巡检帧：robot_frame 新帧 → 现有 YOLO 数据集（只加不重建）。

为什么不直接重跑 export_vision_dataset.py all：
1. 全量重建会重新切分 train/val，历史评估基准漂移，指标不可比；
2. 把已在数据集里的帧重复复制一遍，白耗 IO；
3. 最关键的是**新帧的空 label 在 YOLO 里等于"负样本"**。不跑弱标注就导出，
   等于告诉模型"这些帧一切正常"，一旦实际有异常，比不训练更糟。

所以本脚本只做增量：以 manifest.jsonl 里的 sha256 为唯一真相跳过已导入帧，
新帧统一进 val（时间切分语义：val 代表比训练集更新的"未来"数据），
label 建成空文件，随后由 weak_label_vision.py --skip-existing 生成候选，
回写 labels/ 由人工执行 apply_weak_labels.py 决定。

定时用法：
    python scripts/accumulate_vision_frames.py --data ../data/vision/yolo
    python scripts/weak_label_vision.py --data ../data/vision/yolo \
        --out ../data/vision/weak-dino --box-threshold 0.2 --text-threshold 0.2 --skip-existing

    # 人工复核后再执行回写
    python scripts/apply_weak_labels.py --data ../data/vision/yolo \
        --weak ../data/vision/weak-dino
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.dataset import (  # noqa: E402
    normalize_frame_row,
    read_jsonl,
    select_new_frames,
)

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "vision" / "yolo"
DEFAULT_FRAMES_ROOT = Path(__file__).resolve().parents[2] / "data" / "robot-frames"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}

FRAME_SQL = """
SELECT id AS frame_id, device_key, target, file_path, sha256, bytes,
       width, height, quality, captured_at, simulated
FROM robot_frame
WHERE distilled_at IS NULL
  AND (%(since)s IS NULL OR captured_at >= %(since)s)
ORDER BY captured_at
LIMIT %(limit)s
"""


def load_repo_env() -> None:
    """从仓库根 .env 补齐数据库口令。

    定时任务里没有人工 export，口令只存在于 .env；只用 setdefault 补空缺，
    不覆盖调用方已显式设置的环境变量。
    """
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def db_config() -> dict[str, Any]:
    """连接参数：优先 SMARTOPS_DB_*，回退后端沿用的 MYSQL_*。"""
    load_repo_env()
    return {
        "host": os.getenv("SMARTOPS_DB_HOST") or os.getenv("MYSQL_HOST", "127.0.0.1"),
        "port": int(os.getenv("SMARTOPS_DB_PORT") or os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("SMARTOPS_DB_USER") or os.getenv("MYSQL_USERNAME", "root"),
        "password": os.getenv("SMARTOPS_DB_PASSWORD") or os.getenv("MYSQL_PASSWORD", ""),
        "database": os.getenv("SMARTOPS_DB_NAME") or os.getenv("MYSQL_DATABASE", "smartops"),
    }


def fetch_pending(limit: int, since: str | None) -> list[dict[str, Any]]:
    import pymysql

    connection = pymysql.connect(cursorclass=pymysql.cursors.DictCursor, **db_config())
    try:
        with connection.cursor() as cursor:
            cursor.execute(FRAME_SQL, {"since": since, "limit": limit})
            return list(cursor.fetchall())
    finally:
        connection.close()


def mark_distilled(frame_ids: list[int]) -> int:
    """回写 distilled_at：本轮扫描过的帧全部标记，避免下次重复扫描同一批。"""
    if not frame_ids:
        return 0
    import pymysql

    # 实测坑：pymysql 默认 autocommit=False，连接关闭时未 commit 的 UPDATE 会被
    # 回滚——脚本报告"标记 N 条"但 DB 里 distilled_at 仍是 NULL，且不报错
    connection = pymysql.connect(autocommit=True, **db_config())
    try:
        with connection.cursor() as cursor:
            placeholders = ",".join(["%s"] * len(frame_ids))
            return cursor.execute(
                f"UPDATE robot_frame SET distilled_at=NOW() WHERE id IN ({placeholders})",
                frame_ids,
            )
    finally:
        connection.close()


def known_digests(manifest_path: Path) -> set[str]:
    if not manifest_path.is_file():
        return set()
    return {str(item.get("sha256") or "") for item in read_jsonl(manifest_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="增量积累巡检帧到 YOLO 数据集")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="YOLO 数据集目录")
    parser.add_argument("--frames-root", default=str(DEFAULT_FRAMES_ROOT), help="关键帧归档根目录")
    parser.add_argument("--split", default="val", help="新帧落到的 split（默认 val）")
    parser.add_argument("--limit", type=int, default=2000, help="本轮最多扫描多少条待处理帧")
    parser.add_argument("--limit-new", type=int, default=0, help="本轮最多导入多少张新帧，0 表示不限")
    parser.add_argument("--since", default=None, help="只处理该时间之后的帧（YYYY-MM-DD）")
    parser.add_argument("--min-bytes", type=int, default=1024)
    parser.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--no-mark-db", dest="mark_db", action="store_false")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    data_dir = Path(args.data).resolve()
    if not (data_dir / "data.yaml").is_file():
        print(f"[FAIL] 找不到 data.yaml：{data_dir}")
        return 1

    manifest_path = data_dir / "manifest.jsonl"
    known = known_digests(manifest_path)

    try:
        rows = fetch_pending(args.limit, args.since)
    except Exception as error:  # noqa: BLE001 - DB 不可用要明确报错退出，不静默成功
        print(f"[FAIL] 读取 robot_frame 失败：{error}")
        return 1

    records = [normalize_frame_row(row, args.frames_root) for row in rows]
    kept, skipped = select_new_frames(records, known, args.min_bytes, args.max_bytes)
    if args.limit_new > 0:
        kept = kept[: args.limit_new]

    print(f"数据集   : {data_dir}")
    print(f"待处理帧 : {len(rows)} 条（distilled_at IS NULL）")
    print(f"新增待导入: {len(kept)} 张，跳过 {len(skipped)} 条")
    reasons: dict[str, int] = {}
    for item in skipped:
        reason = str(item.get("skip_reason", "")).split(":")[0]
        reasons[reason] = reasons.get(reason, 0) + 1
    for reason, count in sorted(reasons.items()):
        print(f"  - {reason}: {count}")

    if args.dry_run:
        for record in kept[:10]:
            print(f"  [dry-run] {record['frame_id']} {record['file_path']}")
        print("[OK] dry-run 结束，未写入数据集")
        return 0

    image_dir = data_dir / "images" / args.split
    label_dir = data_dir / "labels" / args.split
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    imported: list[dict[str, Any]] = []
    missing = 0
    for record in kept:
        source = Path(record["file_path"])
        if not source.is_file():
            missing += 1
            continue
        if source.suffix.lower() not in IMAGE_SUFFIXES:
            missing += 1
            continue
        stem = f"{record['frame_id']}_{str(record.get('sha256') or '')[:8]}"
        target = image_dir / f"{stem}{source.suffix.lower()}"
        if target.exists():
            continue  # 幂等：同一帧重复导入直接跳过
        shutil.copyfile(source, target)
        # 空 label = 负样本占位，随后由弱标注产出候选，人工复核后才回写
        (label_dir / f"{stem}.txt").touch()
        imported.append({
            **record,
            "yolo_image": str(target.relative_to(data_dir)),
            "split": args.split,
            "imported_at": datetime.now(timezone.utc).isoformat(),
        })

    if imported:
        with manifest_path.open("a", encoding="utf-8") as handle:
            for item in imported:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")

    marked = 0
    if args.mark_db:
        try:
            marked = mark_distilled([int(row["frame_id"]) for row in rows if row.get("frame_id")])
        except Exception as error:  # noqa: BLE001
            print(f"[WARN] distilled_at 回写失败（不影响已导入的帧）：{error}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": str(data_dir),
        "split": args.split,
        "scanned": len(rows),
        "imported": len(imported),
        "skipped": len(skipped),
        "missing_file": missing,
        "skip_reasons": reasons,
        "marked_distilled": marked,
        "note": "新帧的 label 为空（负样本占位），必须跑弱标注 + 人工复核后再回写",
    }
    report_path = data_dir / "accumulate.report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] 导入 {len(imported)} 张到 {args.split}，文件缺失 {missing} 张，标记 {marked} 条")
    print(f"[OK] 报告：{report_path}")
    if imported:
        print("[NEXT] 生成候选：python scripts/weak_label_vision.py --data "
              f"{args.data} --out ../data/vision/weak-dino --skip-existing")
        print("[NEXT] 人工复核后再回写：python scripts/apply_weak_labels.py --data "
              f"{args.data} --weak ../data/vision/weak-dino")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
