from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .api.router import api_router
from .core.baseline import bootstrap as bootstrap_baseline, teardown as teardown_baseline
from .core.exceptions import AIServiceException
from .core.http_pool import http_pool
from .core.logging import setup_logging
from .core.metrics import mark_build, metrics_endpoint, metrics_middleware

# KV-CACHE 心跳：空闲期定时发超短请求，防止 Ollama 驱逐 KV 缓存
from .services.ollama_heartbeat import heartbeat
# TTS 启动预热：后台预加载本地 TTS 权重，避免首次播报 66s 静默
from .services.tts import tts_preheat


setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：管理共享 HTTP transport + Ollama KV 心跳 + 安全基线。

    startup → security_baseline.bootstrap（fail-closed，哈希链恢复失败则
    抛异常中断启动，绝不让服务以"无审计裸奔"态对外）→ http_pool → heartbeat
    shutdown → heartbeat → http_pool → security_baseline.teardown（只释放引用）
    """
    # SECURITY BASELINE v0：生命周期起点装配（同步 fail-closed）。
    # 装配期间哈希链/清单校验失败时 build_security_baseline 直接抛 ValueError，
    # 让 lifespan 中断、uvicorn 拒绝对外——这是我们故意要求的 fail-closed。
    bootstrap_baseline()

    await http_pool.startup()

    # KV-CACHE 心跳：仅 ollama provider 时 heartbeat.start() 内部会自动跳过
    await heartbeat.start()

    # TTS 启动预热：后台跑，不阻塞 lifespan yield（端口绑定必须先完成，否则前端连不上）
    # PERF-09 经验：同步 await 预热曾导致 FastAPI 端口绑定阻塞 1597 人级预热场景
    import asyncio as _asyncio

    _asyncio.create_task(tts_preheat.start())

    try:
        yield
    finally:
        await heartbeat.stop()
        await http_pool.shutdown()
        # 安全基线 teardown：只释放模块级引用，审计接收器本身无后台线程需要停。
        # 审计哈希链已在进程生命周期内全部 flush+fsync 落盘，进程崩溃不丢。
        teardown_baseline()


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