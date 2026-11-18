"""GroundingDINO 开放词表检测：给类别名，直接出归一化框。

为什么不再让 VLM 出框：
- 实测 `qwen2.5vl:3b` 在 30 帧真实导出的合成帧上把 7/8 个异常帧判成正常，
  召回 12.5%；出框时坐标跨图逐位复读，仅有的一个"命中"也靠巧合；
- 根因不是分类能力，而是小目标在视觉编码后细节基本丢失，
  机房场景的语言先验压倒了画面证据；
- GroundingDINO 是专职检测器：文本提示直接映射到框，
  小目标检出与坐标精度是本职，不依赖模型"会不会描述"。

三条边界：
1. 结果仍是**候选**，写进 weak/ 供人工复核，绝不覆盖 labels/；
2. 类别提示按 GroundingDINO 惯例拼成 "a. b. c." 的短语串，
   返回的 phrase 经归一后反查回类别名，查不到的一律拒绝并留原因；
3. 模型与 processor **懒加载**：import 本模块不能触发 700MB 权重下载，
   pytest 与离线脚本都要能在没有权重时正常导入。
"""

from __future__ import annotations

import os
from typing import Sequence

from app.vision.weak_label import MIN_BOX_SIDE, CandidateBox

DEFAULT_MODEL = os.getenv("GROUNDING_DINO_MODEL", "IDEA-Research/grounding-dino-tiny")
# HuggingFace 直连在国内常态超时，hf-mirror 可用；用户显式设置 HF_ENDPOINT 时以其为准
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")


def _normalize_phrase(text: str) -> str:
    """把短语归一成可比形式：GroundingDINO 返回的 label 会丢标点、改大小写。"""
    return " ".join(text.lower().replace("_", " ").replace("-", " ").split())


def build_text_prompt(class_names: Sequence[str]) -> str:
    """拼成检测器吃的提示串：`person intrusion. obstacle. fire or smoke.`

    类别名里的下划线换成空格：BERT 词表对 `person_intrusion` 会切成子词，
    语义上不如自然短语，实测后者召回更稳。
    """
    phrases = [_normalize_phrase(name) for name in class_names]
    return ". ".join(phrases) + "."


def match_class(label: str, class_names: Sequence[str]) -> tuple[str | None, str | None]:
    """把检测器返回的短语反查回类别名。

    检测器返回的是 detokenize 后的 token span，**经常只是类别名的一部分**：
    实测 "missing extinguisher" 被切成 "extinguisher"，
    "fallen equipment" 被切成 "equipment"。所以做词集合包含匹配；
    一个短语同时落在多个类别上（如 "obstacle extinguisher"）视为歧义并拒绝，
    宁可漏一个候选，也不凭空指定类别污染标签。
    """
    normalized = _normalize_phrase(label)
    by_phrase = {_normalize_phrase(name): name for name in class_names}
    if normalized in by_phrase:
        return by_phrase[normalized], None

    words = set(normalized.split())
    if not words:
        return None, f"未知类别 {label!r}"
    hits = [name for phrase, name in by_phrase.items() if words <= set(phrase.split())]
    if len(hits) == 1:
        return hits[0], None
    if len(hits) > 1:
        return None, f"类别歧义 {label!r} → {', '.join(hits)}"
    return None, f"未知类别 {label!r}"


def nms_keep_indices(
    boxes: Sequence[tuple[float, float, float, float]],
    scores: Sequence[float],
    iou_threshold: float = 0.45,
) -> list[int]:
    """贪心 NMS，返回保留框的下标（按分数降序）。

    为什么必须自己做：GroundingDINO 的 `post_process_grounded_object_detection`
    只做阈值过滤，**不做 NMS**。实测 0.2 阈值下同一目标会出 2~4 个高度重叠的框，
    直接回写成 label 会让训练时的正样本分配被重复框淹没。

    @param boxes 归一化 (cx, cy, w, h)
    """
    order = sorted(range(len(boxes)), key=lambda index: scores[index], reverse=True)
    kept: list[int] = []
    while order:
        current = order.pop(0)
        kept.append(current)
        remaining = []
        for index in order:
            if _iou(boxes[current], boxes[index]) <= iou_threshold:
                remaining.append(index)
        order = remaining
    return kept


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2
    ax2, ay2 = a[0] + a[2] / 2, a[1] + a[3] / 2
    bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2
    bx2, by2 = b[0] + b[2] / 2, b[1] + b[3] / 2
    width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = width * height
    union = a[2] * a[3] + b[2] * b[3] - intersection
    return intersection / union if union > 0 else 0.0


class GroundingDetector:
    """懒加载的 GroundingDINO 封装。

    只在第一次 `detect()` 时加载权重，构造本身零成本——
    这样 CLI 可以在 --dry-run 下完全不碰模型。
    """

    def __init__(self, model_id: str = DEFAULT_MODEL, device: str | None = None) -> None:
        self.model_id = model_id
        self._device = device
        self._processor = None
        self._model = None

    def _ensure_loaded(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_id)
        if self._device is None:
            self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model.to(self._device).eval()

    def detect(
        self,
        image,
        class_names: Sequence[str],
        box_threshold: float = 0.30,
        text_threshold: float = 0.25,
        nms_iou: float = 0.45,
    ) -> tuple[list[CandidateBox], list[str]]:
        """检测一张 PIL 图。

        @return (归一化候选框, 拒绝原因)。坐标是相对整图的 cx/cy/w/h，
                与弱标注产物同构，调用方无需区分后端。同类重叠框已过 NMS。
        """
        import torch

        self._ensure_loaded()
        prompt = build_text_prompt(class_names)
        inputs = self._processor(images=image, text=prompt, return_tensors="pt")
        inputs = {key: value.to(self._device) for key, value in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)

        # transformers 5.x 把 box_threshold 改名为 threshold，这里按签名探测一次
        kwargs = {"threshold": box_threshold, "text_threshold": text_threshold,
                  "target_sizes": [image.size[::-1]]}
        try:
            results = self._processor.post_process_grounded_object_detection(
                outputs, inputs["input_ids"], **kwargs
            )[0]
        except TypeError:
            results = self._processor.post_process_grounded_object_detection(
                outputs, inputs["input_ids"],
                box_threshold=box_threshold, text_threshold=text_threshold,
                target_sizes=[image.size[::-1]],
            )[0]

        width, height = image.size
        accepted: list[CandidateBox] = []
        rejected: list[str] = []

        boxes = results.get("boxes")
        # transformers 5.x 起 `labels` 语义被拆成"整数 id + text_labels 字符串"，
        # 老版本只有 `labels` 字符串；优先取 text_labels，回退 labels
        labels = results.get("text_labels")
        if labels is None:
            labels = results.get("labels")
        if boxes is None or labels is None:
            return accepted, ["检测器返回缺少 boxes/labels"]

        scores = results.get("scores")
        score_list = scores.tolist() if scores is not None else [1.0] * len(labels)

        # 先按类别分组收集，NMS 只在同类内进行：不同类别的重叠框是合法共存
        grouped: dict[str, list[tuple[CandidateBox, float]]] = {}
        for box, label, score in zip(boxes.tolist(), labels, score_list):
            name, problem = match_class(str(label), class_names)
            if name is None:
                rejected.append(problem or f"未知类别 {label!r}")
                continue
            x1, y1, x2, y2 = (float(value) for value in box)
            # 像素坐标 → 归一化中心框，并裁剪到画布内
            x1, x2 = max(0.0, min(width, x1)), min(width, max(0.0, x2))
            y1, y2 = max(0.0, min(height, y1)), min(height, max(0.0, y2))
            w, h = (x2 - x1) / width, (y2 - y1) / height
            if w < MIN_BOX_SIDE or h < MIN_BOX_SIDE:
                rejected.append(f"{name}: 框尺寸过小 ({w:.3f}×{h:.3f})")
                continue
            grouped.setdefault(name, []).append((
                CandidateBox(
                    label=name,
                    cx=round((x1 + x2) / 2 / width, 6),
                    cy=round((y1 + y2) / 2 / height, 6),
                    w=round(w, 6),
                    h=round(h, 6),
                ),
                float(score),
            ))

        for items in grouped.values():
            geometry = [(item[0].cx, item[0].cy, item[0].w, item[0].h) for item in items]
            weights = [item[1] for item in items]
            for index in nms_keep_indices(geometry, weights, nms_iou):
                accepted.append(items[index][0])
        return accepted, rejected
