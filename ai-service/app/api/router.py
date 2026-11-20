from fastapi import APIRouter

from .agent import router as agent_router
from .agent_trigger import router as agent_trigger_router
from .chat import router as chat_router
from .desktop_perceive import router as desktop_perceive_router
from .health import router as health_router
from .nn import router as nn_router
from .orchestrate import router as orchestrate_router
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

# W1：统一 Agent 执行入口（执行链固定挂 L0-L3 安全基线）
api_router.include_router(
    agent_router,
    prefix="/agent",
    tags=["Agent"],
)

# W7：事件驱动 —— Sentinel 告警触发的只读初诊（内部令牌 fail-closed）
api_router.include_router(
    agent_trigger_router,
    prefix="/agent",
    tags=["Agent"],
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

# 阶段 0：多子智能体编排（拆解 → 分波并发 → 结果整合）
api_router.include_router(
    orchestrate_router,
    prefix="/orchestrate",
    tags=["Orchestrate"],
)

# DH-04：桌面手感知（截图 → 元素列表），与 NN 共用 /nn 前缀
api_router.include_router(
    desktop_perceive_router,
    prefix="/nn",
    tags=["NN"],
)