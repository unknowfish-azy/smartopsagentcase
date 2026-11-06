from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .api.router import api_router
from .core.exceptions import AIServiceException
from .core.http_pool import http_pool
from .core.logging import setup_logging
from .core.metrics import mark_build, metrics_endpoint, metrics_middleware


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """PERF-02：共享 HTTP transport 由应用生命周期统一管理。"""
    await http_pool.startup()
    try:
        yield
    finally:
        await http_pool.shutdown()


app = FastAPI(
    title="SmartOpsAgent AI Service",
    description=(
        "智维Agent AI服务，提供LLM、RAG和对话编排能力"
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# PERF-08：Prometheus 抓取路径。中间件记录真实请求与耗时，不做估算。
app.middleware("http")(metrics_middleware)
app.add_api_route("/metrics", metrics_endpoint, methods=["GET"], include_in_schema=False)
mark_build(app.version)


app.include_router(
    api_router,
    prefix="/api",
)


@app.get("/")
async def root():

    return {
        "name": "SmartOpsAgent AI Service",
        "version": "0.1.0",
        "status": "running",
    }


@app.exception_handler(
    AIServiceException
)
async def ai_service_exception_handler(
    request,
    exc: AIServiceException,
):

    return JSONResponse(
        status_code=exc.http_status,
        content={
            "code": exc.code,
            "message": exc.message,
        },
        headers=exc.headers or None,
    )