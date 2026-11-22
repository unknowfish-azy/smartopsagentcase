"""NN-05 视觉 OCR 端点：`GET /api/nn/ocr-info`、`POST /api/nn/ocr`。

缺口清单第六项「OCR 补齐」的落点：视觉侧加 OCR，支撑截图 / 报表识别。

约束（与桌面感知一致）：ai-service 不抓屏，`image_b64` 必须由调用方传入；
**响应里永远没有图片字节**；引擎不可用时返回 `available=false` + 原因，不报 500、不伪造文字。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..vision import ocr as ocr_svc

router = APIRouter()


class OCRBlockModel(BaseModel):
    """一个识别块。"""

    text: str = Field(description="归一化后的文字")
    confidence: float | None = Field(default=None, description="引擎置信度；缺失为 null")
    box: tuple[int, int, int, int] | None = Field(
        default=None, description="像素框 (x0, y0, x1, y1)；引擎未给时为 null"
    )


class OCRRequest(BaseModel):
    image_b64: str = Field(
        min_length=1,
        description="待识别图片（PNG/JPEG）的 base64，可带 data-URI 前缀；必须由调用方传入",
    )
    max_text: int = Field(
        default=ocr_svc.DEFAULT_MAX_TEXT,
        ge=0,
        le=500,
        description="返回文字的最大长度，0 表示不截断；仅截断 text 字段，不影响 blocks",
    )


class OCRResponse(BaseModel):
    available: bool = Field(description="引擎是否可用；false 时 text/blocks 为空")
    ok: bool
    reason: str | None = Field(default=None, description="不可用原因，可用时为 null")
    engine: str = Field(description="引擎名，如 rapidocr / none")
    text: str = Field(description="整图文字（块间以空格连接，已归一化）")
    blocks: list[OCRBlockModel] = Field(default_factory=list)
    confidence: float | None = Field(default=None, description="有置信度的块均值；全无则 null")
    warnings: list[str] = Field(default_factory=list)
    elapsed_ms: int = Field(description="本次识别耗时（毫秒）")


@router.get(
    "/ocr-info",
    summary="查询视觉 OCR 引擎状态",
)
async def ocr_info() -> dict:
    return ocr_svc.get_ocr_info()


@router.post(
    "/ocr",
    response_model=OCRResponse,
    summary="图片 → 文字（不返回图片）",
    description=(
        "输入调用方传入的图（base64），用本地 RapidOCR 识别文字，"
        "输出 text / blocks / confidence。\n\n"
        "约束：ai-service 不抓屏（无系统权限），`image_b64` 必须由调用方传入；"
        "响应不含图片字节，坐标只用于本机解析。\n"
        "引擎未就绪时返回 available=false + reason，不报 500、不伪造识别结果。"
    ),
)
async def ocr(request: OCRRequest) -> OCRResponse:
    try:
        image = ocr_svc.decode_image(request.image_b64)
    except ocr_svc.OCRInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    result = ocr_svc.recognize(image)
    available = result.status != "UNAVAILABLE"
    reason = " ".join(result.warnings) if not available else None
    return OCRResponse(
        available=available,
        ok=available,
        reason=reason,
        engine=result.engine,
        text=ocr_svc.truncate_text(result.text, request.max_text),
        blocks=[OCRBlockModel(text=b.text, confidence=b.confidence, box=b.box) for b in result.blocks],
        confidence=result.confidence,
        warnings=result.warnings,
        elapsed_ms=result.elapsed_ms,
    )
