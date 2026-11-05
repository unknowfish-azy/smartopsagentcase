import json

from fastapi import APIRouter, Depends, Header, Response
from fastapi.responses import StreamingResponse

from ..core.correlation import correlation_headers, resolve_ids
from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
)
from ..services.chat import ChatService

from agent.runtime_events import RunIdentity


router = APIRouter()


def get_chat_service() -> ChatService:
    return ChatService()


def _identity(
    request: ChatRequest,
    header_request_id: str | None,
    header_task_id: str | None,
    header_run_id: str | None,
) -> RunIdentity:
    request_id, task_id, run_id = resolve_ids(
        header_request_id=header_request_id,
        header_task_id=header_task_id,
        header_run_id=header_run_id,
        metadata=request.metadata,
    )
    return RunIdentity.create(
        request_id=request_id,
        task_id=task_id,
        run_id=run_id,
    )


@router.post(
    "",
    response_model=ChatResponse,
)
async def chat(
    request: ChatRequest,
    response: Response,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    x_run_id: str | None = Header(default=None, alias="X-Run-ID"),
    service: ChatService = Depends(
        get_chat_service
    ),
) -> ChatResponse:

    identity = _identity(request, x_request_id, x_task_id, x_run_id)
    response.headers.update(
        correlation_headers(identity.request_id, identity.task_id, identity.run_id)
    )
    return await service.chat(request, identity=identity)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    x_run_id: str | None = Header(default=None, alias="X-Run-ID"),
    service: ChatService = Depends(
        get_chat_service
    ),
):
    """SSE 流式对话端点：前端用 EventSource / fetch 读取 thinking/token/done 事件。"""

    identity = _identity(request, x_request_id, x_task_id, x_run_id)

    async def event_generator():
        async for event in service.chat_stream(request, identity=identity):
            yield (
                f"event: {event['event']}\n"
                f"data: {json.dumps(event['data'], ensure_ascii=False)}\n\n"
            )

    hdr = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
        **correlation_headers(
            identity.request_id,
            identity.task_id,
            identity.run_id,
        ),
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=hdr,
    )
