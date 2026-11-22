"""DH-04 桌面感知服务：截图 → 可交互元素列表。

边界（与 ARCHITECTURE §3 的四条铁律一致）：
1. **不抓屏**：ai-service 没有系统权限，`image_b64` 必须由被控端 driver 截好再传；
2. **不返图**：响应只含元素与耗时，图片字节永不过网络（截图留在调用方落盘）；
3. **不伪造**：模型未就绪 / 推理失败一律返回 `available=false` + 原因，
   不报 500、不产出"看起来能用"的假元素。

定位复用 `app/vision/grounding.py` 的 GroundingDINO：它返回归一化中心框，
这里只做「归一化 → 像素 bbox」「类别 → UIA role」的翻译，不做二次猜测。
"""

from __future__ import annotations

import base64
import binascii
import importlib.util
import io
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from ..vision.grounding import DEFAULT_MODEL, GroundingDetector
from ..vision import ocr as ocr_mod

# 视觉感知的类别表：写死 UI 语义，不引用 vision/classes.py 的巡检预设
# （那三套是机房目标，拿来认按钮只会得到一堆误检）。
GUI_CLASSES: tuple[str, ...] = (
    "button",
    "text field",
    "text box",
    "checkbox",
    "radio button",
    "drop down",
    "menu",
    "menu item",
    "tab",
    "link",
    "icon",
    "list item",
    "slider",
    "scroll bar",
    "toolbar",
    "dialog",
)

# 类别名 → UIA 风格 role。GroundingDINO 只给视觉类别，
# role 是给门禁（R3 白名单按 role 过滤）和 LLM 看的，必须归一成固定词表。
_ROLE_BY_CLASS: dict[str, str] = {
    "button": "button",
    "text field": "edit",
    "text box": "edit",
    "checkbox": "checkbox",
    "radio button": "radiobutton",
    "drop down": "combobox",
    "menu": "menu",
    "menu item": "menuitem",
    "tab": "tabitem",
    "link": "hyperlink",
    "icon": "icon",
    "list item": "listitem",
    "slider": "slider",
    "scroll bar": "scrollbar",
    "toolbar": "toolbar",
    "dialog": "window",
}

DEFAULT_MAX_ELEMENTS = 200
MAX_ELEMENTS_LIMIT = 1000

# OCR 增强（可选，默认关）：开启时整图识别一次，再把文字按框匹配回元素。
# 默认关闭的理由：element_id = hash(window_id+role+name+bbox)，name 若被 OCR 改写，
# 同一控件的 id 会随识别结果漂移、破坏既有契约；开启后 name 仍保持类别名，
# 文字只进 ocr_text（不参与 element_id）。
OCR_TEXT_CLASSES = frozenset(
    {
        "button",
        "text field",
        "text box",
        "checkbox",
        "radio button",
        "menu item",
        "tab",
        "link",
        "list item",
        "dialog",
        "toolbar",
    }
)
DEFAULT_OCR_MIN_CONFIDENCE = 0.5
DEFAULT_OCR_MAX_TEXT = 60

_REQUIRED_MODULES = ("torch", "transformers", "PIL")
_DATA_URI_RE = re.compile(r"^data:image/[A-Za-z0-9.+-]+;base64,")

_detector: GroundingDetector | None = None
_element_id_impl: Callable[..., str] | None = None


class DesktopPerceiveError(ValueError):
    """入参不可用（图片解码失败等），由路由映射成 400。"""


def _missing_modules() -> list[str]:
    """只查依赖是否安装，不 import、不加载权重（import torch 本身就要几秒）。"""
    return [name for name in _REQUIRED_MODULES if importlib.util.find_spec(name) is None]


def _resolve_detector() -> tuple[GroundingDetector | None, str | None]:
    """返回 (检测器, 不可用原因)。不可用时绝不抛异常，交由调用方降级。"""
    missing = _missing_modules()
    if missing:
        return None, (
            f"缺少可选依赖 {', '.join(missing)}"
            "（pip install transformers torch pillow，见 requirements.txt 注释）"
        )

    global _detector
    if _detector is None:
        _detector = GroundingDetector()
    return _detector, None


def _element_id_fn() -> Callable[..., str]:
    """复用 agent 侧的 element_id 实现，绝不在这里另写一套哈希。

    ai-service 与 agent 同仓，按 nn.py 里 orchestrator 的做法把 repo 根塞进 sys.path；
    分成两个服务部署时这里会 ImportError，届时按 available=false 报告，不静默降级。
    """
    global _element_id_impl
    if _element_id_impl is not None:
        return _element_id_impl

    repo_root = Path(__file__).resolve().parents[3]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from agent.desktop.element_id import element_id as implementation

    _element_id_impl = implementation
    return implementation


def decode_image(image_b64: str):
    """base64 / data-URI → RGB 的 PIL 图。失败抛 DesktopPerceiveError（→ 400）。"""
    payload = "".join(image_b64.strip().split())
    payload = _DATA_URI_RE.sub("", payload)
    if not payload:
        raise DesktopPerceiveError("image_b64 为空")

    from PIL import Image

    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DesktopPerceiveError("image_b64 不是合法的 base64") from exc

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()
        return image.convert("RGB")
    except Exception as exc:  # PIL 对坏图抛的异常类型不统一（UnidentifiedImageError/OSError）
        raise DesktopPerceiveError(f"image_b64 无法解码成图片：{exc}") from exc


def _bbox_from_normalized(box: Any, width: int, height: int) -> tuple[int, int, int, int]:
    """归一化中心框 (cx, cy, w, h) → 像素 (x0, y0, x1, y1)，并裁剪到画布内。"""
    x0 = int(round((box.cx - box.w / 2) * width))
    y0 = int(round((box.cy - box.h / 2) * height))
    x1 = int(round((box.cx + box.w / 2) * width))
    y1 = int(round((box.cy + box.h / 2) * height))
    return (
        max(0, min(width, x0)),
        max(0, min(height, y0)),
        max(0, min(width, x1)),
        max(0, min(height, y1)),
    )


def _unavailable(reason: str, window_id: str, started: float) -> dict[str, Any]:
    return {
        "available": False,
        "ok": False,
        "reason": reason,
        "window_id": window_id,
        "elements": [],
        "rejected": [],
        "truncated": False,
        "ocr": None,
        "elapsed_ms": _elapsed_ms(started),
    }


def _elapsed_ms(started: float) -> int:
    return int(round((time.perf_counter() - started) * 1000))


def perceive(
    image_b64: str,
    *,
    window_id: str,
    max_elements: int = DEFAULT_MAX_ELEMENTS,
    class_names: Sequence[str] = GUI_CLASSES,
    ocr_enabled: bool = False,
    ocr_min_confidence: float = DEFAULT_OCR_MIN_CONFIDENCE,
    ocr_max_text: int = DEFAULT_OCR_MAX_TEXT,
) -> dict[str, Any]:
    """对一张截图做元素感知。

    @param image_b64 driver 截图（PNG/JPEG）的 base64，可带 data-URI 前缀。
    @param window_id driver 的窗口 id；element_id = hash(window_id+role+name+bbox)。
    @param max_elements 元素上限，超出部分丢弃并把 truncated 置 True。
    @param ocr_enabled 是否启用 OCR 增强（默认关）：开启时整图识别一次，
        把文字按框匹配回元素并写入 `ocr_text`；`name` 与 `element_id` 不变。
    @param ocr_min_confidence 元素文字只接受置信度不低于该值的块。
    @param ocr_max_text 元素 `ocr_text` 的最大长度，0 表示不截断。
    @return 响应字典（含 elapsed_ms）。图片字节绝不回传。
    """
    started = time.perf_counter()
    image = decode_image(image_b64)
    width, height = image.size

    try:
        make_element_id = _element_id_fn()
    except Exception as exc:  # noqa: BLE001 - 共享契约缺失属于部署事故，按不可用上报
        return _unavailable(f"共享 element_id 实现不可用：{exc}", window_id, started)

    detector, reason = _resolve_detector()
    if detector is None:
        return _unavailable(reason or "感知模型不可用", window_id, started)

    try:
        boxes, rejected = detector.detect(image, class_names)
    except Exception as exc:  # noqa: BLE001 - 权重下载失败/显存不足都要降级，不能 500
        return _unavailable(f"感知模型不可用：{exc}", window_id, started)

    # OCR 增强：整图只识别一次（逐元素裁剪会慢一个数量级，且丢上下文）。
    # 引擎不可用 / 失败时结果是 UNAVAILABLE，直接跳过，绝不编造文字。
    ocr_result = ocr_mod.recognize(image) if ocr_enabled else None

    elements = []
    for box in boxes:
        bbox = _bbox_from_normalized(box, width, height)
        role = _ROLE_BY_CLASS.get(box.label, box.label)
        # 检测器只给类别不给文字，name 先用类别名占位；
        # 开启 OCR 时把识别到的控件文字放进 ocr_text（name/element_id 保持稳定）。
        name = box.label
        ocr_text = None
        if (
            ocr_result is not None
            and ocr_result.status == "SUCCEEDED"
            and box.label in OCR_TEXT_CLASSES
        ):
            matched = ocr_mod.select_text_for_bbox(
                bbox, ocr_result.blocks, min_confidence=ocr_min_confidence
            )
            if matched:
                ocr_text = ocr_mod.truncate_text(matched, ocr_max_text)
        elements.append(
            {
                "element_id": make_element_id(window_id, role, name, bbox),
                "role": role,
                "name": name,
                "bbox": bbox,
                "enabled": True,  # 视觉无法判断灰化状态，交由 driver/UIA 复核
                "ocr_text": ocr_text,
            }
        )

    # 按阅读顺序（先上后下、先左后右）排序，让截断与人工复核行为可预测。
    elements.sort(key=lambda item: (item["bbox"][1], item["bbox"][0]))

    limit = max(1, min(int(max_elements), MAX_ELEMENTS_LIMIT))
    truncated = len(elements) > limit
    if truncated:
        elements = elements[:limit]

    return {
        "available": True,
        "ok": True,
        "reason": None,
        "window_id": window_id,
        "elements": elements,
        "rejected": list(rejected),
        "truncated": truncated,
        "ocr": (
            None
            if ocr_result is None
            else {
                "available": ocr_result.status != "UNAVAILABLE",
                "engine": ocr_result.engine,
                "blocks": len(ocr_result.blocks),
                "confidence": ocr_result.confidence,
            }
        ),
        "elapsed_ms": _elapsed_ms(started),
    }


def get_model_info() -> dict[str, Any]:
    """报告感知模型状态（不加载权重、不联网）。"""
    missing = _missing_modules()
    return {
        "available": not missing,
        "kind": "groundingdino" if not missing else "unavailable",
        "reason": None
        if not missing
        else f"缺少可选依赖 {', '.join(missing)}（pip install transformers torch pillow）",
        "model_id": DEFAULT_MODEL,
        "classes": list(GUI_CLASSES),
        "max_elements_default": DEFAULT_MAX_ELEMENTS,
        "max_elements_limit": MAX_ELEMENTS_LIMIT,
        "ocr": ocr_mod.get_ocr_info(),
        "ocr_text_classes": sorted(OCR_TEXT_CLASSES),
    }
