from pathlib import Path
from statistics import mean

from .base import OCRBlock, OCRResult

class TesseractOCR:
    def __init__(
        self,
        lang: str = "chi_sim+eng",
    ):
        self.lang = lang
        self.psm = 6
        self.scale = 2

    def extract_text(
        self,
        image_path: str,
    ) -> str:

        return self.extract_document(image_path).text

    def extract_document(self, image_path: str) -> OCRResult:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"OCR 图片不存在: {path}")
        try:
            import pytesseract
            from PIL import Image, ImageEnhance, ImageOps
        except ImportError as exc:
            raise RuntimeError("真实 OCR 未启用，请安装 pytesseract、Pillow 和 Tesseract 中文语言包") from exc
        with Image.open(path) as original:
            image = ImageOps.exif_transpose(original).convert("L")
            image = image.resize((image.width * self.scale, image.height * self.scale))
            image = ImageEnhance.Contrast(image).enhance(1.35)
            config = f"--psm {self.psm}"
            text = pytesseract.image_to_string(image, lang=self.lang, config=config).strip()
            data = pytesseract.image_to_data(image, lang=self.lang, config=config, output_type=pytesseract.Output.DICT)
        blocks, confidences = [], []
        for index, raw in enumerate(data.get("text", [])):
            value = str(raw).strip()
            if not value:
                continue
            try:
                confidence = float(data["conf"][index])
            except (KeyError, TypeError, ValueError):
                confidence = None
            if confidence is not None and confidence >= 0:
                confidences.append(confidence)
            blocks.append(OCRBlock(value, confidence, *_numbers(data, index)))
        return OCRResult(text=text, blocks=blocks, language=self.lang,
                         confidence=round(mean(confidences), 2) if confidences else None,
                         engine="tesseract", warnings=[] if text else ["未识别到文字；流程图节点可能需要人工补录"])


def _numbers(data, index):
    values = []
    for key in ("left", "top", "width", "height"):
        try:
            values.append(int(data[key][index]))
        except (KeyError, IndexError, TypeError, ValueError):
            values.append(None)
    return values
