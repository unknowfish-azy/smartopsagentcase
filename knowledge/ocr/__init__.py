"""
SmartOpsAgent Knowledge OCR Module.

负责图片、扫描 PDF 等非结构化内容的文字识别。

支持：
- OCRService：OCR 统一抽象接口
- NoopOCR：未启用 OCR 时的占位实现
- TesseractOCR：基于 Tesseract 的 OCR 实现

OCR 是知识入库流程中的可选能力，不影响普通 TXT、Markdown、
可提取文本的 PDF 等文档的正常处理。
"""

from .base import OCRBlock, OCRResult, OCRService
from .noop import NoopOCR

__all__ = [
    "OCRService",
    "OCRBlock",
    "OCRResult",
    "NoopOCR",
    "TesseractOCR",
]


def __getattr__(name: str):
    # TesseractOCR 依赖 pytesseract / Pillow 以及本机 Tesseract 引擎，
    # 属于可选能力，改为按需延迟导入，避免缺少依赖时崩溃。
    if name == "TesseractOCR":
        from .tesseract import TesseractOCR

        return TesseractOCR

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
