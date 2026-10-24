from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .api.router import api_router
from .core.exceptions import AIServiceException
from .core.logging import setup_logging


setup_logging()


app = FastAPI(
    title="SmartOpsAgent AI Service",
    description=(
        "智维Agent AI服务，提供LLM、RAG和对话编排能力"
    ),
    version="0.1.0",
)


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
        status_code=500,
        content={
            "code": exc.code,
            "message": exc.message,
        },
    )