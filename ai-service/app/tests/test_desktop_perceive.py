"""DH-04 感知端点测试。

不联网、不加载权重：`_resolve_detector` 一律用桩替换，只验证
「base64 → 元素列表」的契约、截断、降级与"不返图"这几条硬约束。
"""

from __future__ import annotations

import base64
import io
import json
import re

import pytest
from PIL import Image

from app.services import desktop_perceive as svc
from app.vision.weak_label import CandidateBox

ELEMENT_ID_RE = re.compile(r"^[a-f0-9]{16}$")


def _png_b64(width: int = 200, height: int = 100) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


class _StubDetector:
    """替身检测器：只回放预设的候选框，不碰 transformers / 权重。"""

    def __init__(self, boxes=(), rejected=(), error: Exception | None = None):
        self._boxes = list(boxes)
        self._rejected = list(rejected)
        self._error = error
        self.calls: list[tuple] = []

    def detect(self, image, class_names, **kwargs):
        self.calls.append((image.size, tuple(class_names)))
        if self._error is not None:
            raise self._error
        return list(self._boxes), list(self._rejected)


@pytest.fixture
def stub_detector(monkeypatch):
    def install(boxes=(), rejected=(), error=None) -> _StubDetector:
        detector = _StubDetector(boxes, rejected, error)
        monkeypatch.setattr(svc, "_resolve_detector", lambda: (detector, None))
        return detector

    return install


def _box(cx: float, cy: float, w: float = 0.2, h: float = 0.2, label: str = "button"):
    return CandidateBox(label=label, cx=cx, cy=cy, w=w, h=h)


def _post(client, **overrides):
    payload = {
        "window_id": "hwnd-1",
        "image_b64": _png_b64(),
        "max_elements": 200,
    }
    payload.update(overrides)
    return client.post("/api/nn/desktop-perceive", json=payload)


def test_模型未就绪返回_available_false(client, monkeypatch):
    monkeypatch.setattr(
        svc, "_resolve_detector", lambda: (None, "缺少可选依赖 torch")
    )

    response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["ok"] is False
    assert "torch" in body["reason"]
    assert body["elements"] == []
    assert body["truncated"] is False
    assert body["elapsed_ms"] >= 0


def test_推理失败降级为_available_false_而不是500(client, stub_detector):
    stub_detector(error=RuntimeError("权重下载失败"))

    response = _post(client)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert "权重下载失败" in body["reason"]
    assert body["elements"] == []


def test_元素字段齐全且_bbox_转成像素(client, stub_detector):
    stub_detector([_box(cx=0.5, cy=0.5, w=0.5, h=0.5)])

    body = _post(client).json()

    assert body["available"] is True
    assert body["truncated"] is False
    assert len(body["elements"]) == 1
    element = body["elements"][0]
    assert element["role"] == "button"
    assert element["name"] == "button"
    assert element["bbox"] == [50, 25, 150, 75]
    assert element["enabled"] is True
    assert ELEMENT_ID_RE.match(element["element_id"])


def test_类别名归一成_UIA_role(client, stub_detector):
    stub_detector([_box(0.5, 0.5, label="text field"), _box(0.2, 0.8, label="menu item")])

    roles = {item["role"] for item in _post(client).json()["elements"]}

    assert roles == {"edit", "menuitem"}


def test_超过上限时截断(client, stub_detector):
    stub_detector([_box(0.1, 0.1), _box(0.4, 0.4), _box(0.8, 0.8)])

    body = _post(client, max_elements=2).json()

    assert len(body["elements"]) == 2
    assert body["truncated"] is True


def test_未超上限不截断(client, stub_detector):
    stub_detector([_box(0.1, 0.1), _box(0.4, 0.4)])

    body = _post(client, max_elements=2).json()

    assert len(body["elements"]) == 2
    assert body["truncated"] is False


def test_按阅读顺序排序(client, stub_detector):
    stub_detector([_box(0.8, 0.8), _box(0.6, 0.2), _box(0.2, 0.5)])

    elements = _post(client).json()["elements"]

    tops = [item["bbox"][1] for item in elements]
    assert tops == sorted(tops)


def test_element_id_同输入稳定且随窗口变化(client, stub_detector):
    stub_detector([_box(0.5, 0.5)])
    image = _png_b64()

    first = _post(client, image_b64=image).json()["elements"][0]["element_id"]
    again = _post(client, image_b64=image).json()["elements"][0]["element_id"]
    other_window = _post(client, image_b64=image, window_id="hwnd-2").json()["elements"][0]["element_id"]

    assert first == again
    assert first != other_window


def test_响应不含图片字节(client, stub_detector):
    stub_detector([_box(0.5, 0.5)])
    image = _png_b64()

    response = _post(client, image_b64=image)

    body = response.json()
    assert "image_b64" not in body
    assert image not in json.dumps(body)
    assert "data:image" not in json.dumps(body)


def test_支持_data_uri_前缀(client, stub_detector):
    stub_detector([_box(0.5, 0.5)])

    response = _post(client, image_b64="data:image/png;base64," + _png_b64())

    assert response.status_code == 200
    assert len(response.json()["elements"]) == 1


def test_非法_base64_返回400(client, stub_detector):
    stub_detector([_box(0.5, 0.5)])

    response = _post(client, image_b64="!!!not-base64!!!")

    assert response.status_code == 400


def test_空元素列表也返回成功(client, stub_detector):
    stub_detector([], rejected=["未知类别 'cat'"])

    body = _post(client).json()

    assert body["available"] is True
    assert body["elements"] == []
    assert body["rejected"] == ["未知类别 'cat'"]


def test_info_端点返回类别表(client):
    response = client.get("/api/nn/desktop-perceive-info")

    assert response.status_code == 200
    body = response.json()
    assert body["model_id"]
    assert "button" in body["classes"]
    assert body["max_elements_limit"] == svc.MAX_ELEMENTS_LIMIT
