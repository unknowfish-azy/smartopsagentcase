import json
import time

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from ..core.config import settings
from ..core.correlation import correlation_headers, resolve_ids
from ..core.run_token import RunTokenError, verify_run_token
from ..schemas.chat import (
    ChatRequest,
    ChatResponse,
)
from ..services.chat import ChatService

from agent.runtime_events import RunIdentity


router = APIRouter()

# SEC-02：一个 run 令牌只代表一次 run，重复使用会被拒绝（409），
# 避免同一 run_id 承载两段不同 payload 导致事件与审计互相覆盖。
_used_tokens: dict[str, int] = {}
_USED_TOKEN_LIMIT = 10_000


def get_chat_service() -> ChatService:
    return ChatService()


def _consume(run_id: str, expires_at: int, now: int) -> bool:
    for key, expiry in list(_used_tokens.items()):
        if expiry <= now:
            _used_tokens.pop(key, None)
    if run_id in _used_tokens:
        return False
    if len(_used_tokens) >= _USED_TOKEN_LIMIT:
        return False
    _used_tokens[run_id] = expires_at
    return True


def require_chat_identity(request: Request) -> dict | None:
    """SEC-01：聊天端点必须携带 Java 边缘签发的短时 run 令牌。

    ``CHAT_ALLOW_ANONYMOUS=true`` 只用于本地/内网联调；默认关闭，
    未配置密钥时返回 503 而不是放行。
    """
    if settings.chat_allow_anonymous:
        return None
    token = request.headers.get("X-Run-Token")
    try:
        identity = verify_run_token(token, settings.chat_run_token_secret)
    except RunTokenError as failure:
        raise HTTPException(status_code=failure.status, detail={"code": failure.code}) from None
    if not _consume(identity["run_id"], identity["expires_at"], int(time.time())):
        raise HTTPException(status_code=409, detail={"code": "RUN_TOKEN_REPLAYED"})
    return identity


def _identity(
    request: ChatRequest,
    header_request_id: str | None,
    header_task_id: str | None,
    token_identity: dict | None,
) -> RunIdentity:
    request_id, task_id, generated_run_id = resolve_ids(
        header_request_id=header_request_id,
        header_task_id=header_task_id,
        metadata=request.metadata,
    )
    # 客户端 ``X-Run-ID`` 只是标签，不得作为 run 身份（SEC-02）。
    run_id = token_identity["run_id"] if token_identity else generated_run_id
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
    identity_token: dict | None = Depends(require_chat_identity),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    service: ChatService = Depends(
        get_chat_service
    ),
) -> ChatResponse:

    identity = _identity(request, x_request_id, x_task_id, identity_token)
    response.headers.update(
        correlation_headers(identity.request_id, identity.task_id, identity.run_id)
    )
    return await service.chat(request, identity=identity)


@router.post("/stream")
async def chat_stream(
    request: ChatRequest,
    identity_token: dict | None = Depends(require_chat_identity),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    service: ChatService = Depends(
        get_chat_service
    ),
):
    """SSE 流式对话端点：前端用 EventSource / fetch 读取 thinking/token/done 事件。"""

    identity = _identity(request, x_request_id, x_task_id, identity_token)

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
