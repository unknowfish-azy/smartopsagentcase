import asyncio
import base64

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ..core.config import settings
from ..core.run_token import RunTokenError, verify_run_token
from ..schemas.tts import TtsStatusResponse, TtsSynthesizeRequest
from ..services.tts import tts_service


router = APIRouter()


def require_tts_identity(request: Request) -> None:
    """TTS 复用聊天 run 令牌校验（SEC-01），但**不消耗 run**。

    语音合成不是一次对话 run，重复播报同一条回复不应该被 409 拒绝；
    这里只验证签名与有效期。``CHAT_ALLOW_ANONYMOUS=true`` 仅限本地联调。
    """
    if settings.chat_allow_anonymous:
        return None
    token = request.headers.get("X-Run-Token")
    try:
        verify_run_token(token, settings.chat_run_token_secret)
    except RunTokenError as failure:
        raise HTTPException(status_code=failure.status, detail={"code": failure.code}) from None
    return None


@router.get(
    "/status",
    response_model=TtsStatusResponse,
)
async def tts_status(_: None = Depends(require_tts_identity)) -> TtsStatusResponse:
    """各 Provider 的真实可用性与不可用原因。

    探测里含网络握手/HTTP 请求（在线音源会做真实连通性测试），必须放到线程池：
    一是不能阻塞事件循环，二是 Provider 内部用 asyncio.run 做一次性探测，
    在事件循环里直接调用会抛 RuntimeError 并泄漏 coroutine。
    """
    return TtsStatusResponse(**await asyncio.to_thread(tts_service.status))


@router.post(
    "/synthesize",
    response_class=Response,
    responses={
        200: {
            "description": "默认二进制音频；请求体 timing=true 时改为 JSON（base64 音频 + 词级时间戳）",
            "content": {"audio/wav": {}, "audio/mpeg": {}, "application/json": {}},
        }
    },
)
async def tts_synthesize(
    payload: TtsSynthesizeRequest,
    _: None = Depends(require_tts_identity),
) -> Response:
    """把文本合成为音频：本地模型回 16-bit 单声道 WAV，在线音源直接回 MP3。

    不可用（依赖缺失/权重未配置/网络不可达/加载失败）返回 503 + 原因；
    模型已加载但本次推理失败返回 502。两种情况下都不会返回占位音频。

    ``timing=true`` 时返回 JSON：``audio_base64`` + ``timing[]``（WordBoundary 词级
    毫秒偏移）。``timing`` 为空表示该 Provider 没有边界事件，前端必须降级为近似口型。
    """
    audio, meta = await tts_service.synthesize(
        payload.text,
        voice=payload.voice,
        speed=payload.speed,
    )
    headers = {
        "Cache-Control": "no-store",
        "X-TTS-Provider": meta["provider"],
        "X-TTS-Voice": meta["voice"],
        "X-TTS-Speed-Applied": "true" if meta["speed_applied"] else "false",
    }
    if payload.timing:
        return JSONResponse(
            content={
                "audio_base64": base64.b64encode(audio).decode("ascii"),
                "media_type": meta["media_type"],
                "provider": meta["provider"],
                "voice": meta["voice"],
                "speed_applied": meta["speed_applied"],
                "timing": meta["timing"],
            },
            headers=headers,
        )
    return Response(content=audio, media_type=meta["media_type"], headers=headers)
