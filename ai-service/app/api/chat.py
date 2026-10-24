from fastapi import APIRouter, Depends

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