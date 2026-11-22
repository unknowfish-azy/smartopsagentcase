"""DH-04 桌面感知端点：`POST /api/nn/desktop-perceive`。

Agent 只想"看见"界面时调这里。输入是被控端 driver 截好的图（base64），
输出是可交互元素列表；**响应里永远没有图片字节**，也不接受坐标。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import desktop_perceive as desktop_perceive_svc

router = APIRouter()


class PerceiveElement(BaseModel):
    """一个可交互元素。字段与 agent/desktop/models.py::UiElement 对齐。"""

    element_id: str = Field(description="hash(window_id + role + name + bbox) 取前 16 hex")
    role: str = Field(description="归一化后的 UIA 风格 role，如 button / edit / menuitem")
    name: str = Field(description="可读名；视觉感知阶段用检测类别名占位，由 UIA/OCR 补齐")
    bbox: tuple[int, int, int, int] = Field(description="像素坐标 (x0, y0, x1, y1)")
    enabled: bool = Field(default=True, description="视觉无法判断灰化，默认 true，由 driver 复核")
    ocr_text: str | None = Field(
        default=None,
        description="OCR 识别到的控件文字；仅在 ocr_enabled=true 时可能非空，不参与 element_id",
    )


class DesktopPerceiveRequest(BaseModel):
    window_id: str = Field(
        min_length=1,
        description="driver 的窗口 id，用于生成稳定 element_id（ai-service 不抓屏）",
    )
    image_b64: str = Field(
        min_length=1,
        description="driver 截图 PNG/JPEG 的 base64（可带 data-URI 前缀）；必须由被控端传入",
    )
    max_elements: int = Field(
        default=desktop_perceive_svc.DEFAULT_MAX_ELEMENTS,
        ge=1,
        le=desktop_perceive_svc.MAX_ELEMENTS_LIMIT,
        description="返回元素上限，超出部分丢弃并置 truncated=true",
    )
    ocr_enabled: bool = Field(
        default=False,
        description=(
            "是否启用 OCR 增强（默认关）：开启时整图识别一次并按框匹配回元素，"
            "写入 ocr_text；name 与 element_id 保持稳定"
        ),
    )
    ocr_min_confidence: float = Field(
        default=desktop_perceive_svc.DEFAULT_OCR_MIN_CONFIDENCE,
        ge=0.0,
        le=1.0,
        description="元素文字只接受置信度不低于该值的识别块",
    )
    ocr_max_text: int = Field(
        default=desktop_perceive_svc.DEFAULT_OCR_MAX_TEXT,
        ge=0,
        le=200,
        description="元素 ocr_text 的最大长度，0 表示不截断",
    )


class DesktopPerceiveResponse(BaseModel):
    available: bool = Field(description="模型是否可用；false 时 elements 必为空")
    ok: bool
    reason: str | None = Field(default=None, description="不可用原因，可用时为 null")
    window_id: str
    elements: list[PerceiveElement] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list, description="检测器拒绝原因，用于排查漏检")
    truncated: bool = False
    ocr: dict | None = Field(
        default=None,
        description="OCR 增强摘要（未启用时为 null）：available/engine/blocks/confidence",
    )
    elapsed_ms: int = Field(description="本次感知耗时（毫秒），DH-08 性能回填用")


@router.get(
    "/desktop-perceive-info",
    summary="查询桌面感知模型状态",
)
async def desktop_perceive_info() -> dict:
    return desktop_perceive_svc.get_model_info()


@router.post(
    "/desktop-perceive",
    response_model=DesktopPerceiveResponse,
    summary="桌面截图 → 可交互元素列表（不返回图片）",
    description=(
        "输入 driver 截好的图（base64），用本地 GroundingDINO 定位可交互元素，"
        "输出 element_id / role / name / bbox / enabled。\n\n"
        "约束：ai-service 不抓屏（无系统权限），`image_b64` 必须由被控端 driver 传入；"
        "响应不含图片字节，坐标只用于本机 driver 解析，不会回传给 LLM。\n"
        "模型未就绪时返回 available=false + reason，不报 500。"
    ),
)
async def desktop_perceive(request: DesktopPerceiveRequest) -> DesktopPerceiveResponse:
    try:
        result = desktop_perceive_svc.perceive(
            request.image_b64,
            window_id=request.window_id,
            max_elements=request.max_elements,
            ocr_enabled=request.ocr_enabled,
            ocr_min_confidence=request.ocr_min_confidence,
            ocr_max_text=request.ocr_max_text,
        )
    except desktop_perceive_svc.DesktopPerceiveError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DesktopPerceiveResponse(**result)
