"""
SmartOpsAgent Knowledge Service（HTTP）。

启动方式：

    uvicorn knowledge.server:app --host 0.0.0.0 --port 8002

提供的接口：

    GET  /api/health      健康检查
    POST /api/search      混合检索
    POST /api/documents   文档摄入
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel, Field

from knowledge.service import KnowledgeService


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    version: str | None = None


class DocumentRequest(BaseModel):
    content: str = Field(min_length=1)
    source: str = ""
    version: str = "latest"
    document_id: str | None = None


app = FastAPI(
    title="SmartOpsAgent Knowledge Service",
    description="知识库服务：文档摄入 + 混合检索 + 证据生成",
    version="0.1.0",
)

service = KnowledgeService()


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "UP",
        "service": "smartops-knowledge-service",
        "version": "0.1.0",
        "chunks": service.chunk_count,
    }


@app.post("/api/search")
async def search(request: SearchRequest) -> dict:
    return service.search(
        request.query,
        top_k=request.top_k,
        version=request.version,
    )


@app.post("/api/documents")
async def add_document(request: DocumentRequest) -> dict:
    count = service.add_document(
        request.content,
        source=request.source,
        version=request.version,
        document_id=request.document_id,
    )

    return {
        "added": count,
        "total_chunks": service.chunk_count,
    }
