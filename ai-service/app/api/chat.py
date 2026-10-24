import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
)
from ..services.chat import ChatService


router = APIRouter()


def get_chat_service() -> ChatService:
    return ChatService()


@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    service: ChatService = Depends(
        get_chat_service
    ),
) -> ChatResponse:

    return await service.chat(request)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    service: ChatService = Depends(
        get_chat_service
    ),
):
    """SSE 流式对话端点：前端用 EventSource / fetch 读取 thinking/token/done 事件。"""

    async def event_generator():
        async for event in service.chat_stream(request):
            yield (
                f"event: {event['event']}\n"
                f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )