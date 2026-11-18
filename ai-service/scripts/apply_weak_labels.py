"""把可信的候选框回写成 YOLO 初标（只追加，先备份）。

为什么只回写部分类别：
实测 GroundingDINO 在 `fire_or_smoke` 上 7/8 命中、22 张正常帧零误报，
但 `missing_extinguisher` / `fallen_equipment` 会把服务器本体框成
"缺失灭火器 / 倒地设备"，属于系统性误检。全量回写等于把误检钉进真值。

用法（在 ai-service 目录下执行）：

    # 1) 先看会改哪些帧、加几个框
    python scripts/apply_weak_labels.py --data ../data/vision/yolo \
        --weak ../data/vision/weak-dino --dry-run

    # 2) 正式回写（原 label 先备份到 <data>/.label-backup/<时间戳>/）
    python scripts/apply_weak_labels.py --data ../data/vision/yolo \
        --weak ../data/vision/weak-dino

    # 3) 误写后回滚：把备份目录里的 txt 拷回 labels/ 对应 split 即可

四条边界：
1. 白名单默认只有 `fire_or_smoke`，要回写别的类别必须显式 --classes；
2. 写前先备份原文件，备份目录按时间戳隔离，可整目录回滚；
3. 只追加不覆盖：人工已标的行原样保留，重复行跳过，重复执行幂等；
4. 产物是**初标**：候选框尺寸偏大约 2 倍（模型框住了烟雾团），
   报告固定写明需人工微调，不宣称已是真值。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.vision.weak_label import load_class_names, merge_candidate_lines  # noqa: E402

DEFAULT_DATA = Path(__file__).resolve().parents[2] / "data" / "vision" / "yolo"
DEFAULT_CLASSES = "fire_or_smoke"


def backup_label(target: Path, labels_dir: Path, backup_root: Path) -> Path:
    """把原 label 复制到备份目录，保留 split 层级，便于整目录回滚。"""
    destination = backup_root / target.relative_to(labels_dir)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target, destination)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser(description="回写可信候选框为 YOLO 初标")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="YOLO 数据集目录（含 data.yaml）")
    parser.add_argument("--weak", default="", help="候选目录，默认 <data>/weak")
    parser.add_argument("--classes", default=DEFAULT_CLASSES, help="回写的类别名，逗号分隔")
    parser.add_argument("--backup-root", default="", help="备份根目录，默认 <data>/.label-backup")
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

    wanted = [name.strip() for name in args.classes.split(",") if name.strip()]
    unknown = [name for name in wanted if name not in class_names]
    if unknown:
        # 拼错类别名会让本轮"成功改了 0 个文件"，必须直接失败而不是静默放过
        print(f"[FAIL] 类别不在 data.yaml 中：{', '.join(unknown)}")
        print(f"       可用类别：{', '.join(class_names)}")
        return 1
    allowed_ids = {class_names.index(name) for name in wanted}

    weak_dir = Path(args.weak).resolve() if args.weak else data_dir / "weak"
    weak_labels_dir = weak_dir / "labels"
    if not weak_labels_dir.is_dir():
        print(f"[FAIL] 候选目录不存在：{weak_labels_dir}（先跑 weak_label_vision.py）")
        return 1

    labels_dir = data_dir / "labels"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = (
        Path(args.backup_root).resolve() if args.backup_root
        else data_dir / ".label-backup" / timestamp
    )

    print(f"数据集 : {data_dir}")
    print(f"候选   : {weak_dir}")
    print(f"回写   : {', '.join(wanted)}（class_id {sorted(allowed_ids)}）")
    print(f"备份   : {backup_root}")
    if args.dry_run:
        print("模式   : dry-run（不写文件）")

    splits = sorted(path.name for path in weak_labels_dir.iterdir() if path.is_dir())
    files: list[dict] = []
    changed = 0
    missing_target = 0
    total_added = 0

    for split in splits:
        for candidate_path in sorted((weak_labels_dir / split).glob("*.txt")):
            target = labels_dir / split / candidate_path.name
            record: dict = {"split": split, "image": candidate_path.name}
            if not target.is_file():
                # 候选与数据集不匹配时明确记账：不凭空创建 label，避免造出无图标签
                missing_target += 1
                record.update({"status": "missing_target", "added": 0})
                files.append(record)
                continue

            existing = target.read_text(encoding="utf-8")
            candidate = candidate_path.read_text(encoding="utf-8")
            merged, added, skipped = merge_candidate_lines(existing, candidate, allowed_ids)
            record.update({"added": added, "skipped": skipped})
            if added == 0:
                record["status"] = "unchanged"
                files.append(record)
                continue

            changed += 1
            total_added += added
            record["status"] = "dry_run" if args.dry_run else "applied"
            if not args.dry_run:
                record["backup"] = str(backup_label(target, labels_dir, backup_root))
                target.write_text(merged, encoding="utf-8")
            files.append(record)
            print(f"  {split}/{candidate_path.name} → +{added} 框")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "data": str(data_dir),
        "weak": str(weak_dir),
        "classes": wanted,
        "class_ids": sorted(allowed_ids),
        "dry_run": bool(args.dry_run),
        "backup_root": None if args.dry_run else str(backup_root),
        "summary": {
            "files_scanned": len(files),
            "files_changed": changed,
            "files_missing_target": missing_target,
            "boxes_added": total_added,
        },
        "note": "候选框是初标：尺寸普遍偏大（模型框住了烟雾与告警标志），需人工微调后才是真值",
        "files": files,
    }
    report_path = weak_dir / "apply.report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"[OK] 扫描 {len(files)} 个候选文件，改动 {changed} 个，"
        f"新增 {total_added} 个框，缺对应图片 {missing_target} 个"
    )
    print(f"[OK] 报告：{report_path}")
    if args.dry_run:
        print("[OK] dry-run 结束，未写入 labels/")
    elif changed:
        print(f"[OK] 回滚方式：把 {backup_root} 下的 txt 拷回 {labels_dir} 对应 split")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
