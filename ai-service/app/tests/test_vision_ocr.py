"""NN-05 视觉 OCR 测试。

分两层：
1. **纯函数与降级契约**（不加载引擎、不联网）：归一化、裁剪、框匹配、
   引擎缺失时返回 UNAVAILABLE 而不是伪造；
2. **真实引擎冒烟**（`importorskip`）：装了 rapidocr_onnxruntime 才跑，
   没装就跳过——绝不用合成结果冒充引擎可用。
"""

from __future__ import annotations

import base64
import io

import pytest
from PIL import Image

from app.services import desktop_perceive as svc
from app.vision import ocr as ocr_mod
from app.vision.ocr import OCRBlock, OCRResult


# ---------------------------------------------------------------- 纯函数

def test_normalize_text_折叠空白并去零宽():
    assert ocr_mod.normalize_text(" 打开  知识库\u200b ") == "打开 知识库"


def test_normalize_text_空输入返回空():
    assert ocr_mod.normalize_text("") == ""
    assert ocr_mod.normalize_text(None) == ""  # type: ignore[arg-type]


def test_truncate_text_超长截断():
    assert ocr_mod.truncate_text("abcdefghij", 5) == "abcd…"


def test_truncate_text_未超长不截断_且limit为0不截断():
    assert ocr_mod.truncate_text("abc", 5) == "abc"
    assert ocr_mod.truncate_text("abcdefghij", 0) == "abcdefghij"


def test_clip_bbox_正常裁剪():
    image = Image.new("RGB", (200, 100), "white")
    cropped = ocr_mod.clip_bbox(image, (50, 25, 150, 75))
    assert cropped is not None
    assert cropped.size == (104, 54)  # padding=2


def test_clip_bbox_越界自动收敛():
    image = Image.new("RGB", (100, 100), "white")
    cropped = ocr_mod.clip_bbox(image, (-20, -20, 1000, 1000))
    assert cropped is not None
    assert cropped.size == (100, 100)


def test_clip_bbox_退化框返回_none():
    image = Image.new("RGB", (100, 100), "white")
    assert ocr_mod.clip_bbox(image, (50, 50, 50, 60)) is None


def test_mean_confidence_全无置信度返回_none而不是0():
    assert ocr_mod.mean_confidence([OCRBlock(text="a"), OCRBlock(text="b")]) is None


def test_select_text_for_bbox_块落在框内被选中():
    blocks = [OCRBlock(text="保存", confidence=0.9, box=(10, 10, 30, 30))]
    assert ocr_mod.select_text_for_bbox((5, 5, 40, 40), blocks) == "保存"


def test_select_text_for_bbox_块不相交返回_none():
    blocks = [OCRBlock(text="保存", confidence=0.9, box=(200, 200, 230, 230))]
    assert ocr_mod.select_text_for_bbox((5, 5, 40, 40), blocks) is None


def test_select_text_for_bbox_低于置信度阈值的块被过滤():
    blocks = [OCRBlock(text="保存", confidence=0.3, box=(10, 10, 30, 30))]
    assert ocr_mod.select_text_for_bbox((5, 5, 40, 40), blocks, min_confidence=0.5) is None


def test_select_text_for_bbox_多块取置信度最高():
    blocks = [
        OCRBlock(text="低", confidence=0.4, box=(10, 10, 30, 30)),
        OCRBlock(text="高", confidence=0.95, box=(12, 12, 28, 28)),
    ]
    assert ocr_mod.select_text_for_bbox((5, 5, 40, 40), blocks) == "高"


# ---------------------------------------------------------------- 降级契约

def test_noop_引擎返回_unavailable而不是伪造文字():
    result = ocr_mod.NoopOCREngine().recognize(Image.new("RGB", (10, 10)))
    assert result.status == "UNAVAILABLE"
    assert result.text == ""
    assert result.warnings


def test_recognize_引擎不可用时返回_unavailable_不抛异常(monkeypatch):
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (None, "缺少可选依赖"))
    result = ocr_mod.recognize(Image.new("RGB", (10, 10)))
    assert result.status == "UNAVAILABLE"
    assert result.text == ""
    assert "缺少可选依赖" in " ".join(result.warnings)


def test_get_ocr_info_字段齐全():
    info = ocr_mod.get_ocr_info()
    assert {"available", "kind", "reason", "engine"} <= set(info)


# ---------------------------------------------------------------- 端点契约

def _png_b64(width: int = 100, height: int = 50) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class _StubEngine:
    name = "stub"

    def __init__(self, result: OCRResult):
        self._result = result
        self.calls = 0

    def recognize(self, image):
        self.calls += 1
        return self._result


def test_ocr端点_用桩引擎返回文字与块(client, monkeypatch):
    stub = _StubEngine(
        OCRResult(
            text="打开知识库",
            blocks=[OCRBlock(text="打开知识库", confidence=0.9, box=(1, 2, 3, 4))],
            confidence=0.9,
            engine="stub",
        )
    )
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (stub, None))

    body = client.post("/api/nn/ocr", json={"image_b64": _png_b64()}).json()

    assert body["available"] is True
    assert body["ok"] is True
    assert body["engine"] == "stub"
    assert body["text"] == "打开知识库"
    assert body["blocks"][0]["text"] == "打开知识库"
    assert body["blocks"][0]["box"] == [1, 2, 3, 4]
    assert body["elapsed_ms"] >= 0


def test_ocr端点_响应不含图片字节(client, monkeypatch):
    import json

    stub = _StubEngine(OCRResult(text="x", engine="stub"))
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (stub, None))
    image = _png_b64()

    raw = client.post("/api/nn/ocr", json={"image_b64": image}).text

    assert image not in raw
    assert "data:image" not in raw
    assert "image_b64" not in json.loads(raw)


def test_ocr端点_引擎不可用返回available_false而不是500(client, monkeypatch):
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (None, "缺少可选依赖"))

    response = client.post("/api/nn/ocr", json={"image_b64": _png_b64()})

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["text"] == ""
    assert "缺少可选依赖" in body["reason"]


def test_ocr端点_非法base64返回400(client, monkeypatch):
    stub = _StubEngine(OCRResult(text="x", engine="stub"))
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (stub, None))

    response = client.post("/api/nn/ocr", json={"image_b64": "!!!not-base64!!!"})

    assert response.status_code == 400


def test_ocr_info端点可访问(client):
    body = client.get("/api/nn/ocr-info").json()
    assert "available" in body
    assert "engine" in body


# ------------------------------------------------- 桌面感知的 OCR 增强

class _StubDetector:
    def __init__(self, boxes):
        self._boxes = list(boxes)

    def detect(self, image, class_names, **kwargs):
        return list(self._boxes), []


def test_感知默认不启用ocr_且element_id稳定(client, monkeypatch):
    from app.vision.weak_label import CandidateBox

    monkeypatch.setattr(
        svc, "_resolve_detector", lambda: (_StubDetector([CandidateBox(label="button", cx=0.5, cy=0.5, w=0.2, h=0.2)]), None)
    )

    body = client.post(
        "/api/nn/desktop-perceive",
        json={"window_id": "hwnd-1", "image_b64": _png_b64()},
    ).json()

    element = body["elements"][0]
    assert element["ocr_text"] is None
    assert element["name"] == "button"
    assert body["ocr"] is None


def test_感知开启ocr_写ocr_text但不改element_id(client, monkeypatch):
    from app.vision.weak_label import CandidateBox

    monkeypatch.setattr(
        svc,
        "_resolve_detector",
        lambda: (_StubDetector([CandidateBox(label="button", cx=0.5, cy=0.5, w=0.2, h=0.2)]), None),
    )
    stub = _StubEngine(
        OCRResult(
            text="登录",
            blocks=[OCRBlock(text="登录", confidence=0.95, box=(45, 22, 55, 28))],
            confidence=0.95,
            engine="stub",
        )
    )
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (stub, None))

    payload = {"window_id": "hwnd-1", "image_b64": _png_b64(), "ocr_enabled": True}
    with_ocr = client.post("/api/nn/desktop-perceive", json=payload).json()

    # 同一窗口、同一图，关闭 OCR 时 element_id 必须一致（ocr_text 不参与哈希）
    without = client.post(
        "/api/nn/desktop-perceive",
        json={"window_id": "hwnd-1", "image_b64": _png_b64()},
    ).json()

    element = with_ocr["elements"][0]
    assert element["ocr_text"] == "登录"
    assert element["name"] == "button"  # name 不被 OCR 改写
    assert element["element_id"] == without["elements"][0]["element_id"]
    assert with_ocr["ocr"]["available"] is True
    assert with_ocr["ocr"]["blocks"] == 1


def test_感知开启ocr_引擎不可用时不影响检测(client, monkeypatch):
    from app.vision.weak_label import CandidateBox

    monkeypatch.setattr(
        svc,
        "_resolve_detector",
        lambda: (_StubDetector([CandidateBox(label="button", cx=0.5, cy=0.5, w=0.2, h=0.2)]), None),
    )
    monkeypatch.setattr(ocr_mod, "resolve_engine", lambda: (None, "缺少可选依赖"))

    body = client.post(
        "/api/nn/desktop-perceive",
        json={"window_id": "hwnd-1", "image_b64": _png_b64(), "ocr_enabled": True},
    ).json()

    assert body["available"] is True
    assert body["elements"][0]["ocr_text"] is None
    assert body["ocr"]["available"] is False


# ------------------------------------------------------- 真实引擎冒烟

def test_真实引擎识别中文字():
    pytest.importorskip("rapidocr_onnxruntime")
    ocr_mod.reset_engine()

    from PIL import ImageDraw, ImageFont

    image = Image.new("RGB", (400, 80), "white")
    draw = ImageDraw.Draw(image)
    font = None
    for path in ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf"):
        try:
            font = ImageFont.truetype(path, 28)
            break
        except OSError:
            continue
    draw.text((10, 20), "打开知识库", fill="black", font=font)

    result = ocr_mod.recognize(image)

    assert result.status == "SUCCEEDED"
    assert result.engine == "rapidocr"
    assert "打开知识库" in result.text.replace(" ", "")
    assert result.confidence is not None and result.confidence > 0.5
    assert result.blocks
