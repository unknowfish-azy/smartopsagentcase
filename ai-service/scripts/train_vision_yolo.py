"""YOLO 训练（本地 GPU/CPU，ultralytics）。

用法（在 ai-service 目录下执行）：

    # 先自检数据集形状，不训练（无 torch 环境也能跑）
    python scripts/train_vision_yolo.py --data ../data/vision/yolo/data.yaml --dry-run

    # 真训练
    python scripts/train_vision_yolo.py --data ../data/vision/yolo/data.yaml \
        --model yolov8n.pt --epochs 60 --imgsz 640 --device 0 --out ../data/vision/runs

为什么不把 ultralytics 写进主依赖：
推理侧（后端视觉巡检）走的是本地 VLM，不依赖 YOLO；训练是离线动作，
装 torch+ultralytics 会显著拉大镜像。因此这里**懒加载**，缺依赖时给出可执行的安装提示，
而不是让整个 ai-service 起不来。

产物：
- {out}/vision_yolo/weights/best.pt
- {out}/vision_yolo/report.json（超参 + 最终指标，用于横向比较与回滚）
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _parse_yaml_names(data_yaml: Path) -> list[str]:
    """只解析 names 段，避免为自检引入 PyYAML。

    兼容两种写法（本项目导出的是第二种）：
        names: {0: a, 1: b}
        names:
          0: a
          1: b
    """
    names: dict[int, str] = {}
    in_names = False
    for line in data_yaml.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("names:"):
            inline = stripped[len("names:"):].strip()
            if inline.startswith("{"):
                body = inline.strip("{}")
                for pair in body.split(","):
                    if ":" in pair:
                        key, value = pair.split(":", 1)
                        names[int(key.strip())] = value.strip().strip("'\"")
                in_names = False
            else:
                in_names = True
            continue
        if in_names:
            if not line.startswith((" ", "\t")):
                in_names = False
                continue
            if ":" not in stripped:
                continue
            key, value = stripped.split(":", 1)
            try:
                names[int(key.strip())] = value.strip().strip("'\"")
            except ValueError:
                in_names = False
    return [names[index] for index in sorted(names)]


def check_dataset(data_yaml: Path) -> dict[str, Any]:
    """自检：data.yaml 可解析、train/val 目录存在且有图。不满足就不要浪费时间训练。"""
    if not data_yaml.is_file():
        raise SystemExit(f"data.yaml 不存在：{data_yaml}")
    classes = _parse_yaml_names(data_yaml)
    if not classes:
        raise SystemExit(f"{data_yaml} 里没有解析到 names，请检查导出结果")

    root = data_yaml.parent
    counts: dict[str, int] = {}
    for split, relative in (("train", "images/train"), ("val", "images/val")):
        directory = root / relative
        counts[split] = sum(1 for item in directory.glob("*") if item.is_file()) if directory.is_dir() else 0

    if counts["train"] == 0:
        raise SystemExit(f"{root / 'images/train'} 没有图片，先跑 export_vision_dataset.py")
    if counts["val"] == 0:
        print("警告：val 为空，训练无法给出泛化指标（建议 --val-ratio >= 0.1 重新导出）")
    print(f"数据集自检通过：{counts['train']} train / {counts['val']} val，{len(classes)} 类：{', '.join(classes)}")
    return {"classes": classes, "counts": counts}


def main() -> None:
    parser = argparse.ArgumentParser(description="YOLO 训练（ultralytics）")
    parser.add_argument("--data", required=True, help="YOLO data.yaml 路径")
    parser.add_argument("--model", default="yolov8n.pt", help="预训练权重或上一次的 best.pt")
    parser.add_argument("--epochs", type=int, default=60)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=-1, help="-1 交给 ultralytics 自适应显存")
    parser.add_argument("--device", default="", help="'' 自动 / 0 / 0,1 / cpu")
    parser.add_argument("--out", default="../data/vision/runs", help="训练产物根目录")
    parser.add_argument("--name", default="vision_yolo")
    parser.add_argument("--dry-run", action="store_true", help="只做数据集自检，不训练")
    args = parser.parse_args()

    data_yaml = Path(args.data)
    info = check_dataset(data_yaml)
    if args.dry_run:
        print("dry-run：跳过训练")
        return

    try:
        from ultralytics import YOLO
    except ImportError:
        raise SystemExit(
            "缺少 ultralytics。请先安装：\n"
            "  pip install ultralytics\n"
            "（会一并安装 torch；CPU 也能训，但批次要小）"
        )

    model = YOLO(args.model)
    results = model.train(
        data=str(data_yaml),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device or None,
        project=str(Path(args.out)),
        name=args.name,
        exist_ok=True,
    )

    metrics: dict[str, Any] = {}
    # ultralytics 的 results_dict 键名随版本变化，逐个尝试并只保留数值
    for candidate in (
        getattr(results, "results_dict", None),
        getattr(getattr(model, "metrics", None), "results_dict", None),
    ):
        if isinstance(candidate, dict):
            metrics.update({str(key): float(value) for key, value in candidate.items()
                            if isinstance(value, (int, float))})
            break

    report = {
        "data": str(data_yaml),
        "classes": info["classes"],
        "dataset_counts": info["counts"],
        "hyperparams": {
            "model": args.model,
            "epochs": args.epochs,
            "imgsz": args.imgsz,
            "batch": args.batch,
            "device": args.device or "auto",
        },
        "metrics": metrics,
        "weights": str(Path(args.out) / args.name / "weights" / "best.pt"),
    }
    report_path = Path(args.out) / f"{args.name}_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"训练完成，报告 {report_path}")
    if metrics:
        print("关键指标：" + ", ".join(f"{key}={value:.4f}" for key, value in list(metrics.items())[:6]))


if __name__ == "__main__":
    main()
