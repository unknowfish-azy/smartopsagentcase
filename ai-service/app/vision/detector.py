"""torchvision FasterRCNN 检测器（BSD-3-Clause）。

替换背景：仓库原有的两个 `.pt` 权重由 Ultralytics 产出，checkpoint 内嵌
`license=AGPL-3.0`（见 `reports/detector-license-audit-2026-11-20.md`）。
本模块是该连接的替代实现，**不 import ultralytics**，训练/推理全走 torchvision。

三条设计约束：
1. **模块导入零开销**：`torch` / `torchvision` 只在方法内部导入，
   `app.vision` 被别的服务 import 时不会连带加载 700MB 的运行时。
2. **不可用要明说**：缺依赖、缺权重一律抛 `DetectorUnavailable`（带原因），
   由调用方降级；不返回空列表冒充"画面干净"。
3. **输出与预测引擎对齐**：`Detection.bbox` 是归一化 `(x1, y1, x2, y2)`，
   可直接喂给 `POST /api/nn/vision-forecast` 的 `frames[].detections`。

不做什么：不做跟踪、不做事件判定（那是 `app/services/vision_forecast.py`），
不读数据库、不写文件、不下载权重（权重由训练脚本产出或显式指定）。
"""

from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

BACKEND = "torchvision.fasterrcnn_mobilenet_v3_large_fpn"
LICENSE = "BSD-3-Clause"


class DetectorUnavailable(RuntimeError):
    """检测器不可用（缺依赖 / 缺权重 / 权重损坏）。消息里必须带原因。"""


@dataclass(frozen=True)
class Detection:
    """与 `app/schemas/vision_forecast.py::Detection` 同形。"""

    label: str
    confidence: float
    bbox: tuple[float, float, float, float]


def runtime_status() -> dict[str, Any]:
    """探测当前环境能否跑 torchvision 检测器（不加载模型、不下载权重）。"""
    has_torch = importlib.util.find_spec("torch") is not None
    has_torchvision = importlib.util.find_spec("torchvision") is not None

    reason: str | None = None
    torch_version = torchvision_version = None
    if not has_torch:
        reason = "缺少 torch"
    elif not has_torchvision:
        reason = "缺少 torchvision"
    else:
        import torch
        import torchvision

        torch_version = torch.__version__
        torchvision_version = torchvision.__version__

    return {
        "available": reason is None,
        "backend": BACKEND,
        "license": LICENSE,
        "reason": reason,
        "torch": torch_version,
        "torchvision": torchvision_version,
    }


def normalize_boxes(
    boxes: Sequence[Sequence[float]],
    width: int,
    height: int,
) -> list[tuple[float, float, float, float]]:
    """像素框 → 归一化框；越界裁剪，退化框（面积 0）直接丢弃。

    丢退化框而不是保留：宽高为 0 的框进了跟踪器只会产生假 ID。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"图像尺寸非法：{width}x{height}")

    normalized: list[tuple[float, float, float, float]] = []
    for raw in boxes:
        x1, y1, x2, y2 = (float(value) for value in raw[:4])
        x1, x2 = sorted((max(0.0, min(1.0, x1 / width)), max(0.0, min(1.0, x2 / width))))
        y1, y2 = sorted((max(0.0, min(1.0, y1 / height)), max(0.0, min(1.0, y2 / height))))
        if x2 - x1 <= 0 or y2 - y1 <= 0:
            continue
        normalized.append((x1, y1, x2, y2))
    return normalized


class TorchvisionDetector:
    """单帧检测器。构造不加载模型，首次 `detect` 才建图。

    参数
    ----
    weights_path: 训练脚本产出的 `model.pt`（纯 state_dict）。为 None 时用 COCO 预训练头，
        只适合冒烟，不适合巡检类别。
    class_names: 类别名（下标 0 → 模型输出 label 1）。与 `weights_path` 同目录的
        `model.json` 存在时优先读它，避免调用方两处维护。
    pretrained: 是否加载 COCO 预训练权重。离线环境/单测可设 False。
    num_classes: 仅 `pretrained=False` 或自定义权重时有意义；默认 len(class_names)+1。
    """

    def __init__(
        self,
        weights_path: Path | str | None = None,
        class_names: Sequence[str] | None = None,
        *,
        score_threshold: float = 0.35,
        device: str | None = None,
        pretrained: bool = True,
        num_classes: int | None = None,
    ) -> None:
        self.weights_path = Path(weights_path) if weights_path else None
        self.score_threshold = score_threshold
        self.device_name = device
        self.pretrained = pretrained
        self.num_classes = num_classes
        self._labels: list[str] = list(class_names or [])
        self._model: Any = None
        self._device: Any = None

    # -- 状态 ---------------------------------------------------------------

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def info(self) -> dict[str, Any]:
        status = runtime_status()
        return {
            **status,
            "loaded": self.loaded,
            "weights_path": str(self.weights_path) if self.weights_path else None,
            "num_classes": self.num_classes or (len(self._labels) + 1 if self._labels else None),
            "score_threshold": self.score_threshold,
        }

    def _load_sidecar(self) -> None:
        """读 `<weights>.json` 里的类别名。缺失不算错误。"""
        if not self.weights_path:
            return
        sidecar = self.weights_path.with_suffix(".json")
        if not sidecar.is_file():
            return
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        classes = payload.get("classes")
        if isinstance(classes, list) and classes:
            self._labels = [str(name) for name in classes]
        if self.num_classes in (None, 0):
            saved = payload.get("num_classes")
            if isinstance(saved, int) and saved > 0:
                self.num_classes = saved

    # -- 模型 ---------------------------------------------------------------

    def _ensure_loaded(self) -> Any:
        if self._model is not None:
            return self._model

        status = runtime_status()
        if not status["available"]:
            raise DetectorUnavailable(str(status["reason"]))

        import torch
        from torchvision.models.detection import (
            FasterRCNN_MobileNet_V3_Large_FPN_Weights,
            fasterrcnn_mobilenet_v3_large_fpn,
        )

        self._load_sidecar()

        if self.weights_path is None:
            classes = self.num_classes or (len(self._labels) + 1 if self._labels else None)
            if self.pretrained:
                weights = FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1
                model = fasterrcnn_mobilenet_v3_large_fpn(
                    weights=weights,
                    num_classes=classes,
                )
                if not self._labels:
                    self._labels = list(weights.meta.get("categories", []))[1:]
            else:
                model = fasterrcnn_mobilenet_v3_large_fpn(
                    weights=None,
                    weights_backbone=None,
                    num_classes=classes or 2,
                )
        else:
            if not self.weights_path.is_file():
                raise DetectorUnavailable(f"权重不存在：{self.weights_path}")
            classes = self.num_classes or (len(self._labels) + 1 if self._labels else 2)
            model = fasterrcnn_mobilenet_v3_large_fpn(
                weights=None,
                weights_backbone=None,
                num_classes=classes,
            )
            try:
                state_dict = torch.load(self.weights_path, map_location="cpu", weights_only=True)
            except Exception as error:  # 权重损坏要带原因，不裸抛 500
                raise DetectorUnavailable(f"权重无法读取：{self.weights_path}（{error}）") from error
            model.load_state_dict(state_dict)
            self.num_classes = classes

        self._device = torch.device(self.device_name or "cpu")
        model.to(self._device)
        model.eval()
        self._model = model
        return model

    # -- 推理 ---------------------------------------------------------------

    def detect(self, image: Any) -> list[Detection]:
        """输入 HxWx3 uint8 RGB（numpy 或 torch），返回归一化检测列表。"""
        model = self._ensure_loaded()

        import numpy as np
        import torch

        array = np.asarray(image)
        if array.ndim != 3 or array.shape[2] not in (3, 4):
            raise ValueError(f"图像必须是 HxWx3/4，实际 {array.shape}")
        array = array[:, :, :3]
        height, width = int(array.shape[0]), int(array.shape[1])

        tensor = torch.from_numpy(array).permute(2, 0, 1).float()
        if tensor.max() > 1.0:
            tensor = tensor / 255.0
        tensor = tensor.to(self._device)

        with torch.no_grad():
            outputs = model([tensor])
        output = outputs[0]

        boxes = normalize_boxes(output["boxes"].tolist(), width, height)
        scores = output["scores"].tolist()
        labels = output["labels"].tolist()

        detections: list[Detection] = []
        for (x1, y1, x2, y2), score, label_id in zip(boxes, scores, labels):
            if score < self.score_threshold:
                continue
            detections.append(
                Detection(
                    label=self._label_of(int(label_id)),
                    confidence=round(float(score), 4),
                    bbox=(round(x1, 5), round(y1, 5), round(x2, 5), round(y2, 5)),
                )
            )
        return detections

    def _label_of(self, label_id: int) -> str:
        index = label_id - 1
        if 0 <= index < len(self._labels):
            return self._labels[index]
        return f"class_{label_id}"


def detector_info() -> dict[str, Any]:
    """给 API / Agent 用的静态能力描述（不实例化模型）。"""
    return {
        **runtime_status(),
        "supports": ["single_frame_detection", "normalized_bbox"],
        "note": "模型需先由 ai-service/scripts/train_vision_frcnn.py 训练产出；未训练时仅 COCO 预训练可用",
    }
