"""NN-06 情绪识别输入端点：`GET /api/nn/emotion-info`、`POST /api/nn/emotion`。

缺口清单 P2-8「数字人三短板」收口项：把用户文本识别成情绪标签，
供前端叠加到 `personaStates.js` 的 expressions 权重（渲染层不改）。

约束：
- **不伪造**：引擎不可用返回 `available=false` + 原因，不报 500、不编造标签；
- **不冒充**：模型本质是情感极性二分类，响应里如实标注维度限制；
- 输入必须是调用方传入的文本，本端点不抓屏、不录音。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..emotion import engine as emotion_svc

router = APIRouter()


class EmotionRequest(BaseModel):
    text: str = Field(min_length=1, description="待识别的用户文本（ASR 转写或输入）")
    max_text: int = Field(
        default=emotion_svc.DEFAULT_MAX_TEXT,
        ge=0,
        le=500,
        description="参与识别的最大字符数，0 表示不截断",
    )


class EmotionResponse(BaseModel):
    available: bool = Field(description="是否有可用引擎；false 时 label 恒为 neutral")
    ok: bool
    reason: str | None = Field(default=None, description="不可用原因，可用时为 null")
    engine: str = Field(description="实际来源：composite+lexicon / composite+model / lexicon / none")
    status: str = Field(description="引擎状态：SUCCEEDED / EMPTY / UNAVAILABLE")
    label: str = Field(description="情绪标签：happy/sad/angry/surprised/neutral")
    confidence: float | None = Field(default=None, description="置信度；未知为 null，不写 0")
    scores: dict[str, float] = Field(default_factory=dict, description="各标签分数（模型路径）")
    warnings: list[str] = Field(default_factory=list)
    elapsed_ms: int = Field(description="本次识别耗时（毫秒）")


@router.get(
    "/emotion-info",
    summary="查询情绪识别引擎状态",
)
async def emotion_info() -> dict:
    return emotion_svc.get_emotion_info()


@router.post(
    "/emotion",
    response_model=EmotionResponse,
    summary="文本 → 情绪标签",
    description=(
        "输入调用方传入的文本（ASR 转写或用户输入），输出情绪标签 + 置信度。\n\n"
        "引擎栈：强情绪词优先 → 本地情感模型（极性二分类，仅 happy/sad）→ 弱词 → neutral。\n"
        "引擎不可用时返回 available=false + 原因，不伪造标签。"
    ),
)
async def emotion(request: EmotionRequest) -> EmotionResponse:
    try:
        result = emotion_svc.recognize(request.text, max_text=request.max_text)
    except emotion_svc.EmotionInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    available = result.status != "UNAVAILABLE"
    reason = " ".join(result.warnings) if not available else None
    return EmotionResponse(
        available=available,
        ok=available,
        reason=reason,
        engine=result.engine or "none",
        status=result.status,
        label=result.label,
        confidence=result.confidence,
        scores=result.scores,
        warnings=result.warnings,
        elapsed_ms=result.elapsed_ms,
    )
