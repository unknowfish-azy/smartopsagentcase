"""视觉侧 OCR：截图 / 报表 → 文字（RapidOCR onnxruntime）。

缺口清单第六项「OCR 补齐」的落点。三条边界（与 ARCHITECTURE §3 的铁律一致）：

1. **不抓屏**：`image` 必须由调用方（driver / 客户端）传入，本模块不访问系统屏幕；
2. **不返图**：结果只含文字、置信度与坐标，图片字节永不过网络；
3. **不伪造**：引擎缺失 / 推理失败一律 `available=false` + 原因，
   不产出"看起来像识别结果"的模拟文字。

与 `knowledge/ocr/` 的分工：那边是**知识入库**侧（图片笔记 → 知识候选，Tesseract 骨架、
未接入）；本模块是**视觉感知**侧（截图元素 / 报表 → 文字），引擎为 RapidOCR，
两条链路各自独立，不互相 import。

懒加载：`import app.vision.ocr` 不触发模型加载（实测约 2.5s），
pytest 与离线脚本在无引擎环境也能正常导入。
"""

from __future__ import annotations

import base64
import binascii
import importlib.util
import io
import re
import time
import unicodedata
from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Sequence

# 引擎缺失时调用方据此返回 available=false，不抛 500、不伪造。
_REQUIRED_MODULES = ("rapidocr_onnxruntime", "numpy")

DEFAULT_MAX_TEXT = 60
DEFAULT_MIN_CONFIDENCE = 0.0

_DATA_URI_RE = re.compile(r"^data:image/[A-Za-z0-9.+-]+;base64,")


class OCREngineUnavailable(RuntimeError):
    """OCR 引擎不可用（缺依赖 / 权重加载失败），由调用方降级。"""


class OCRInputError(ValueError):
    """入参不可用（图片解码失败等），由路由映射成 400。"""


def decode_image(image_b64: str):
    """base64 / data-URI → RGB 的 PIL 图。失败抛 OCRInputError（→ 400）。

    与 `desktop_perceive.decode_image` 同口径（同样不返图、不抓屏），
    但各自实现：OCR 路由不依赖桌面感知模块，避免无谓耦合。
    """
    payload = "".join(str(image_b64).strip().split())
    payload = _DATA_URI_RE.sub("", payload)
    if not payload:
        raise OCRInputError("image_b64 为空")

    from PIL import Image

    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise OCRInputError("image_b64 不是合法的 base64") from exc

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image.convert("RGB")
    except Exception as exc:  # PIL 对坏图抛的异常类型不统一
        raise OCRInputError(f"image_b64 无法解码成图片：{exc}") from exc


@dataclass(frozen=True)
class OCRBlock:
    """一个识别块：文字 + 置信度 + 像素框。"""

    text: str
    confidence: float | None = None
    box: tuple[int, int, int, int] | None = None  # (x0, y0, x1, y1)


@dataclass(frozen=True)
class OCRResult:
    """一次识别的结果。`status` 取 `SUCCEEDED` / `EMPTY` / `UNAVAILABLE`。"""

    text: str
    blocks: list[OCRBlock] = field(default_factory=list)
    confidence: float | None = None
    engine: str = ""
    status: str = "SUCCEEDED"
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0


class OCREngine:
    """OCR 引擎抽象。实现方只需返回 OCRResult，不负责降级文案。"""

    name = "abstract"

    def recognize(self, image: Any) -> OCRResult:  # pragma: no cover - 抽象
        raise NotImplementedError


def missing_modules() -> list[str]:
    """只查依赖是否安装，不 import、不加载权重。"""
    return [name for name in _REQUIRED_MODULES if importlib.util.find_spec(name) is None]


class NoopOCREngine(OCREngine):
    """未启用 OCR 时的占位：明确报不可用，绝不编造文字。"""

    name = "noop"

    def recognize(self, image: Any) -> OCRResult:
        return OCRResult(
            text="",
            engine=self.name,
            status="UNAVAILABLE",
            warnings=["OCR 引擎未启用（缺少 rapidocr_onnxruntime）"],
        )


class RapidOCREngine(OCREngine):
    """RapidOCR（onnxruntime）实现。构造不加载权重，首次 `recognize` 才加载。"""

    name = "rapidocr"

    def __init__(self) -> None:
        self._impl = None

    def _load(self):
        if self._impl is None:
            from rapidocr_onnxruntime import RapidOCR

            self._impl = RapidOCR()
        return self._impl

    def recognize(self, image: Any) -> OCRResult:
        started = time.perf_counter()
        try:
            engine = self._load()
        except Exception as exc:  # noqa: BLE001 - 权重/依赖问题统一降级
            raise OCREngineUnavailable(f"RapidOCR 加载失败：{exc}") from exc

        array = _to_bgr_array(image)
        try:
            result, _elapse = engine(array)
        except Exception as exc:  # noqa: BLE001 - 推理失败按不可用上报
            raise OCREngineUnavailable(f"RapidOCR 推理失败：{exc}") from exc

        blocks: list[OCRBlock] = []
        for item in result or []:
            box, text, confidence = _parse_item(item)
            text = normalize_text(text)
            if not text:
                continue
            blocks.append(OCRBlock(text=text, confidence=confidence, box=box))

        text = normalize_text(" ".join(block.text for block in blocks))
        warnings = [] if text else ["未识别到文字"]
        return OCRResult(
            text=text,
            blocks=blocks,
            confidence=mean_confidence(blocks),
            engine=self.name,
            status="SUCCEEDED" if text else "EMPTY",
            warnings=warnings,
            elapsed_ms=_elapsed_ms(started),
        )


_engine: OCREngine | None = None
_engine_reason: str | None = None
_engine_resolved = False


def resolve_engine() -> tuple[OCREngine | None, str | None]:
    """返回 (引擎, 不可用原因)。首次调用解析并缓存；不抛异常。"""
    global _engine, _engine_reason, _engine_resolved
    if _engine_resolved:
        return _engine, _engine_reason

    missing = missing_modules()
    if missing:
        _engine = None
        _engine_reason = (
            f"缺少可选依赖 {', '.join(missing)}"
            "（pip install rapidocr-onnxruntime，见 ai-service/requirements.txt 注释）"
        )
    else:
        _engine = RapidOCREngine()
        _engine_reason = None
    _engine_resolved = True
    return _engine, _engine_reason


def reset_engine() -> None:
    """测试用：清掉缓存的引擎（不影响已加载的底层实现）。"""
    global _engine, _engine_reason, _engine_resolved
    _engine = None
    _engine_reason = None
    _engine_resolved = False


def recognize(
    image: Any,
    *,
    engine: OCREngine | None = None,
) -> OCRResult:
    """对一张图做 OCR。引擎不可用时返回 `status=UNAVAILABLE`，不抛异常。"""
    started = time.perf_counter()
    if engine is not None:
        resolved, reason = engine, None
    else:
        resolved, reason = resolve_engine()
    if resolved is None:
        reason = reason or _engine_reason or "OCR 引擎不可用"
        return OCRResult(
            text="",
            engine="none",
            status="UNAVAILABLE",
            warnings=[reason],
            elapsed_ms=_elapsed_ms(started),
        )
    try:
        return resolved.recognize(image)
    except OCREngineUnavailable as exc:
        return OCRResult(
            text="",
            engine=getattr(resolved, "name", "unknown"),
            status="UNAVAILABLE",
            warnings=[str(exc)],
            elapsed_ms=_elapsed_ms(started),
        )


# ---------------------------------------------------------------- 纯函数

def normalize_text(text: str) -> str:
    """归一化识别文字：NFKC + 折叠空白 + 去零宽字符。

    不做标点删除：截图里的标点（路径、命令、版本号）是有效信息，
    删掉会掩盖识别错误。归一化只用于让"同一句话"可比。
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", str(text))
    text = text.replace("\u200b", "").replace("\ufeff", "")
    return " ".join(text.split())


def truncate_text(text: str, limit: int = DEFAULT_MAX_TEXT) -> str:
    """截断到 limit 字符，超出加省略号。limit<=0 视为不截断。"""
    if limit <= 0 or len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def clip_bbox(image: Any, bbox: Sequence[int], padding: int = 2):
    """从 PIL 图上裁出像素框，越界自动收敛。

    返回 `PIL.Image.Image`；框退化（宽/高 <= 0）时返回 `None`（调用方应跳过 OCR，
    不把空图喂给引擎）。`image` 必须是已解码的 PIL 图。
    """
    if image is None:
        return None
    width, height = image.size
    x0, y0, x1, y1 = (int(v) for v in bbox)
    # 退化框先判（padding 之前）：零宽/零高的框加 padding 会"复活"成细条，
    # 那不是有效控件区域，交给调用方跳过。
    if x1 <= x0 or y1 <= y0:
        return None
    x0 = max(0, min(width, x0 - padding))
    y0 = max(0, min(height, y0 - padding))
    x1 = max(0, min(width, x1 + padding))
    y1 = max(0, min(height, y1 + padding))
    if x1 <= x0 or y1 <= y0:
        return None
    return image.crop((x0, y0, x1, y1))


def mean_confidence(blocks: Sequence[OCRBlock]) -> float | None:
    """有置信度的块取均值；全无则 None（不写 0，避免把"未知"写成"低分"）。"""
    values = [b.confidence for b in blocks if b.confidence is not None]
    return round(mean(values), 4) if values else None


def select_text_for_bbox(
    bbox: Sequence[int],
    blocks: Sequence[OCRBlock],
    *,
    min_confidence: float = 0.0,
) -> str | None:
    """给一个元素框挑出最可能属于它的识别文字。

    判据：块与框的**交集面积占块面积比例 ≥ 0.5**（块基本落在框内），
    取满足条件里置信度最高的一块。没有块的框返回 None——
    绝不把相邻元素的文字安到本元素上（宁可空着，交给 UIA / 人工）。
    """
    x0, y0, x1, y1 = (int(v) for v in bbox)
    best: OCRBlock | None = None
    for block in blocks:
        if block.box is None:
            continue
        if block.confidence is not None and block.confidence < min_confidence:
            continue
        bx0, by0, bx1, by1 = block.box
        inter_w = max(0, min(x1, bx1) - max(x0, bx0))
        inter_h = max(0, min(y1, by1) - max(y0, by0))
        block_area = max(1, (bx1 - bx0) * (by1 - by0))
        if inter_w * inter_h < 0.5 * block_area:
            continue
        if best is None or (block.confidence or 0.0) >= (best.confidence or 0.0):
            best = block
    return normalize_text(best.text) if best else None


def get_ocr_info() -> dict[str, Any]:
    """报告 OCR 引擎状态（不加载权重、不联网）。"""
    missing = missing_modules()
    available = not missing
    return {
        "available": available,
        "kind": "rapidocr" if available else "unavailable",
        "reason": None
        if available
        else f"缺少可选依赖 {', '.join(missing)}（pip install rapidocr-onnxruntime）",
        "engine": "rapidocr_onnxruntime" if available else None,
        "max_text_default": DEFAULT_MAX_TEXT,
        "min_confidence_default": DEFAULT_MIN_CONFIDENCE,
    }


# ---------------------------------------------------------------- 内部

def _to_bgr_array(image: Any):
    """PIL 图 / ndarray → RapidOCR 吃的 BGR ndarray。"""
    import numpy as np

    if isinstance(image, np.ndarray):
        return image
    rgb = image.convert("RGB")
    arr = np.asarray(rgb)
    return arr[:, :, ::-1]


def _parse_item(item: Any) -> tuple[tuple[int, int, int, int] | None, str, float | None]:
    """解析 RapidOCR 的 `[box(4点), text, confidence]` 结构。"""
    if isinstance(item, (list, tuple)) and len(item) >= 3:
        box_raw, text, confidence = item[0], item[1], item[2]
    elif isinstance(item, dict):
        box_raw = item.get("box") or item.get("boxs")
        text = item.get("text", "")
        confidence = item.get("confidence") or item.get("score")
    else:  # 结构不符：不猜，留空由调用方丢弃
        return None, "", None

    box = _box_from_points(box_raw)
    try:
        conf = float(confidence) if confidence is not None else None
    except (TypeError, ValueError):
        conf = None
    return box, str(text or ""), conf


def _box_from_points(points: Any) -> tuple[int, int, int, int] | None:
    """4 点框 → (x0, y0, x1, y1)；点数不足返回 None。"""
    if not isinstance(points, (list, tuple)) or len(points) < 4:
        return None
    try:
        xs = [float(p[0]) for p in points]
        ys = [float(p[1]) for p in points]
    except (TypeError, IndexError, ValueError):
        return None
    return int(round(min(xs))), int(round(min(ys))), int(round(max(xs))), int(round(max(ys)))


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))
