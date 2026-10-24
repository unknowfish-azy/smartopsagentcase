from fastapi import APIRouter

from ..schemas.health import HealthResponse


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
    )