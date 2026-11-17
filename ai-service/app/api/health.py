from fastapi import APIRouter

from ..schemas.health import HealthResponse
from ..services.ollama_heartbeat import heartbeat


router = APIRouter()


@router.get(
    "",
    response_model=HealthResponse,
)
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="UP",
        service="smartops-ai-service",
        version="0.1.0",
        # KV-CACHE 心跳实时状态：total_beats 随空闲保活递增，可据此观察心跳节奏
        heartbeat=heartbeat.status,
    )