"""用 torchvision FasterRCNN 训练巡检检测器（BSD-3，替代 AGPL 的 ultralytics）。

为什么重写训练脚本，而不是继续用 `train_vision_yolo.py`：
原脚本 `from ultralytics import YOLO`，而 Ultralytics 是 AGPL-3.0，两个产出权重
的 checkpoint 里内嵌 `license=AGPL-3.0`（见 reports/detector-license-audit-2026-11-20.md）。
本脚本用 torchvision 的 `fasterrcnn_mobilenet_v3_large_fpn`（BSD-3 代码，
COCO 预训练）在**同一份 YOLO 格式数据集**上训练，产出可直接被
`app/vision/detector.py::TorchvisionDetector` 加载的权重。

用法：

    # 1) 只做数据自检（不需要 torch，不训练）
    python scripts/train_vision_frcnn.py --data data/vision/dataset/data.yaml --dry-run

    # 2) 正式训练（CPU 也能跑，慢）
    python scripts/train_vision_frcnn.py --data data/vision/dataset/data.yaml \
        --epochs 20 --batch 2 --imgsz 640 --out data/vision/runs --name frcnn-v1

产出：
    {out}/{name}/model.pt    纯 state_dict（weights_only=True 可安全加载）
    {out}/{name}/model.json  类别名、超参、指标（detector 读它拿 label）
    {out}/{name}/run.json    与 model.json 同内容，供训练账本/报告引用

刻意不做的事（避免把"没跑"说成"跑了"）：
1. 不算 mAP——需要 pycocotools，未安装就不算，报告里写 `NOT_RUN`；
2. 不做数据增强——巡检场景的增广要先有基线再谈，先把链路跑通；
3. 不自动写训练账本——加 `--ledger` 才写，避免无 MySQL 环境下静默失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = Path(__file__).resolve().parents[1]
for candidate in (str(AI_SERVICE), str(REPO_ROOT)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.vision.dataset import (  # noqa: E402
    IMAGE_SUFFIXES,
    dataset_health,
    label_path_for,
    parse_yolo_labels,
    read_data_yaml,
)

BASE_MODEL = "fasterrcnn_mobilenet_v3_large_fpn"
LICENSE = "BSD-3-Clause"


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="torchvision FasterRCNN 巡检检测器训练")
    parser.add_argument("--data", required=True, help="data.yaml（images/ labels/ 同级）")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--imgsz", type=int, default=640, help="缩放到正方形边长（会拉伸）")
    parser.add_argument("--lr", type=float, default=0.002)
    parser.add_argument("--device", default="cpu", help="cpu / cuda / cuda:0")
    parser.add_argument("--out", default="data/vision/runs")
    parser.add_argument("--name", default="")
    parser.add_argument("--limit", type=int, default=0, help="仅用前 N 张图（冒烟用）")
    parser.add_argument("--dry-run", action="store_true", help="只做数据自检，不训练")
    parser.add_argument("--force", action="store_true", help="数据自检有问题也继续")
    parser.add_argument("--ledger", action="store_true", help="写入训练账本（需 MySQL 或自动降级 JSONL）")
    parser.add_argument("--no-pretrained", action="store_true", help="不加载 COCO 预训练（离线环境）")
    return parser


def _list_samples(image_dir: Path, limit: int = 0) -> list[tuple[Path, Path]]:
    if not image_dir.is_dir():
        return []
    images = sorted(path for path in image_dir.glob("*") if path.suffix.lower() in IMAGE_SUFFIXES)
    if limit > 0:
        images = images[:limit]
    return [(image, label_path_for(image)) for image in images]


def _run_ledger(payload: dict[str, Any]) -> str:
    """尽力记账；失败不影响训练产物，但要如实打印。"""
    try:
        from training_ledger import record_training_run
    except Exception as error:  # noqa: BLE001
        return f"SKIPPED（{type(error).__name__}: {error}）"
    run_id = record_training_run(
        base_model=BASE_MODEL,
        method="frcnn-finetune",
        params=payload.get("params", {}),
        metrics=payload.get("metrics", {}),
        artifact_uri=payload.get("artifact_uri"),
    )
    return f"OK run_id={run_id}" if run_id is not None else "OK（JSONL 降级）"


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    health = dataset_health(args.data)
    print(json.dumps(health, ensure_ascii=False, indent=2))
    if not health["ok"] and not args.force:
        print("\n数据自检未通过，已中止。修正后重试，或用 --force 强行继续。", file=sys.stderr)
        return 2
    if any(not stats["images"] for stats in health["splits"].values()):
        print("\n存在空的 split，无法训练。", file=sys.stderr)
        return 2
    if args.dry_run:
        print("\ndry-run：跳过训练")
        return 0

    try:
        import torch
        from torch.utils.data import DataLoader, Dataset
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_fpn,
        )
        from torchvision.transforms import functional as TF
        from PIL import Image
    except ImportError as error:
        print(f"缺少训练依赖：{error}\n  pip install torch torchvision pillow", file=sys.stderr)
        return 2

    parsed = read_data_yaml(args.data)
    classes: list[str] = parsed["classes"]
    num_classes = len(classes) + 1  # +1 是背景

    class YoloDetectionDataset(Dataset):  # type: ignore[misc]
        """YOLO 目录 → FasterRCNN 目标；框拉伸到 imgsz 正方形，与图像变换一致。"""

        def __init__(self, image_dir: Path, limit: int = 0) -> None:
            self.samples = _list_samples(image_dir, limit)

        def __len__(self) -> int:
            return len(self.samples)

        def __getitem__(self, index: int):
            image_path, label_path = self.samples[index]
            image = Image.open(image_path).convert("RGB")
            width, height = image.size
            image = TF.resize(image, [args.imgsz, args.imgsz])
            tensor = TF.pil_to_tensor(image).float() / 255.0

            boxes: list[list[float]] = []
            labels: list[int] = []
            for class_id, cx, cy, box_w, box_h in parse_yolo_labels(label_path):
                boxes.append([
                    (cx - box_w / 2) * args.imgsz,
                    (cy - box_h / 2) * args.imgsz,
                    (cx + box_w / 2) * args.imgsz,
                    (cy + box_h / 2) * args.imgsz,
                ])
                labels.append(class_id + 1)  # 0 留给背景

            target = {
                "boxes": torch.tensor(boxes, dtype=torch.float32).reshape(-1, 4),
                "labels": torch.tensor(labels, dtype=torch.int64),
                "image_id": torch.tensor([index]),
                "area": torch.tensor(
                    [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes], dtype=torch.float32
                ).reshape(-1),
                "iscrowd": torch.zeros(len(boxes), dtype=torch.int64),
            }
            _ = (width, height)  # 保留原始尺寸仅用于调试
            return tensor, target

    def collate(batch):
        return tuple(zip(*batch))

    train_ds = YoloDetectionDataset(parsed["splits"]["train"], args.limit)
    val_ds = YoloDetectionDataset(parsed["splits"].get("val", parsed["splits"]["train"]), args.limit)
    if not len(train_ds):
        print("训练集为空。", file=sys.stderr)
        return 2

    if args.no_pretrained:
        model = fasterrcnn_mobilenet_v3_large_fpn(
            weights=None, weights_backbone=None, num_classes=num_classes
        )
    else:
        model = fasterrcnn_mobilenet_v3_large_fpn(
            weights=FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1,
            num_classes=num_classes,
        )

    device = torch.device(args.device)
    model.to(device)
    optimizer = torch.optim.SGD(
        [p for p in model.parameters() if p.requires_grad], lr=args.lr, momentum=0.9, weight_decay=5e-4
    )
    train_loader = DataLoader(train_ds, batch_size=args.batch, shuffle=True, collate_fn=collate)
    val_loader = DataLoader(val_ds, batch_size=1, shuffle=False, collate_fn=collate)

    print(f"[train] imgs={len(train_ds)} val={len(val_ds)} classes={num_classes - 1} device={device}")
    history: list[dict[str, Any]] = []
    for epoch in range(args.epochs):
        model.train()
        running = 0.0
        for images, targets in train_loader:
            images = [image.to(device) for image in images]
            targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
            loss_dict = model(images, targets)
            loss = sum(value for value in loss_dict.values())
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            running += float(loss.detach())
        train_loss = running / max(1, len(train_loader))

        val_loss = 0.0
        model.train()  # torchvision 的检测模型只有 train 模式才返回 loss
        with torch.no_grad():
            for images, targets in val_loader:
                images = [image.to(device) for image in images]
                targets = [{k: v.to(device) for k, v in t.items()} for t in targets]
                loss_dict = model(images, targets)
                val_loss += float(sum(value for value in loss_dict.values()))
        val_loss = val_loss / max(1, len(val_loader))

        history.append({"epoch": epoch + 1, "train_loss": round(train_loss, 4), "val_loss": round(val_loss, 4)})
        print(f"[epoch {epoch + 1}/{args.epochs}] train_loss={train_loss:.4f} val_loss={val_loss:.4f}")

    name = args.name or datetime.now(timezone.utc).strftime("frcnn-%Y%m%d-%H%M%S")
    out_dir = Path(args.out) / name
    out_dir.mkdir(parents=True, exist_ok=True)

    model.eval()
    torch.save(model.state_dict(), out_dir / "model.pt")  # 纯张量，weights_only=True 可读

    payload: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_model": BASE_MODEL,
        "license": LICENSE,
        "classes": classes,
        "num_classes": num_classes,
        "imgsz": args.imgsz,
        "params": {
            "epochs": args.epochs,
            "batch": args.batch,
            "imgsz": args.imgsz,
            "lr": args.lr,
            "device": str(device),
            "pretrained": not args.no_pretrained,
            "torch": torch.__version__,
        },
        "metrics": {
            "train_images": len(train_ds),
            "val_images": len(val_ds),
            "history": history,
            "final_train_loss": history[-1]["train_loss"] if history else None,
            "final_val_loss": history[-1]["val_loss"] if history else None,
            # 没算就是没算：mAP 需要 pycocotools，未提供时不编造数字
            "mAP": "NOT_RUN",
        },
        "artifact_uri": str((out_dir / "model.pt").resolve().as_posix()),
    }
    for target in ("model.json", "run.json"):
        (out_dir / target).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[done] 权重 {out_dir / 'model.pt'}")
    print(f"[done] 类别 {out_dir / 'model.json'}")
    if args.ledger:
        print(f"[ledger] {_run_ledger(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
