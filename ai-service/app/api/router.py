from fastapi import APIRouter

from .chat import router as chat_router
from .health import router as health_router
from .nn import router as nn_router
from .tts import router as tts_router


api_router = APIRouter()

api_router.include_router(
    health_router,
    prefix="/health",
    tags=["Health"],
)

api_router.include_router(
    chat_router,
    prefix="/chat",
    tags=["Chat"],
)

api_router.include_router(
    tts_router,
    prefix="/tts",
    tags=["TTS"],
)

# P0-1：神经网络能力（AnomalyTransformer + 后续 GNN / TinyBERT 都挂这里）
api_router.include_router(
    nn_router,
    prefix="/nn",
    tags=["NN"],
)