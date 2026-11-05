"""
SmartOpsAgent Knowledge Service（HTTP）。

启动方式：

    uvicorn knowledge.server:app --host 0.0.0.0 --port 8002

提供的接口：

    GET  /api/health      健康检查（/health 为同内容别名）
    POST /api/search      混合检索
    POST /api/documents   文档摄入

启动时默认加载 knowledge/reference/ops-knowledge-rag 下的课程语料：

    KNOWLEDGE_SEED_REFERENCE=0           关闭自动加载
    KNOWLEDGE_REFERENCE_DIR=<dir>        指定其他语料目录

访问控制：

    KNOWLEDGE_API_KEY=<key>              开启鉴权，检索/摄入需带 X-API-Key
    KNOWLEDGE_ALLOW_INGEST=1             未配置 key 时允许匿名摄入（默认关闭）
"""

from __future__ import annotations

import logging
import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from knowledge.corpus_manifest import verify_snapshot
from knowledge.config import KnowledgeConfig
from knowledge.service import KnowledgeService

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    version: str | None = None
    # 以下字段不传或 None 表示沿用 service 默认值 / 不做过滤。
    source: str | None = Field(default=None, description="按 source 前缀或子串过滤")
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    vector_weight: float | None = Field(default=None, ge=0.0, le=1.0)
    bm25_weight: float | None = Field(default=None, ge=0.0, le=1.0)


class DocumentRequest(BaseModel):
    content: str = Field(min_length=1)
    source: str = ""
    version: str = "latest"
    document_id: str | None = None


# ----------------------------------------------------------------------
# 访问控制
#
#   KNOWLEDGE_API_KEY      设置后，检索与摄入都必须携带 X-API-Key 头。
#   KNOWLEDGE_ALLOW_INGEST 未设置 key 时，摄入默认关闭（仅本地演示可显式开启）。
# ----------------------------------------------------------------------

_API_KEY_ENV = "KNOWLEDGE_API_KEY"
_ALLOW_INGEST_ENV = "KNOWLEDGE_ALLOW_INGEST"
_TRUTHY = {"1", "true", "yes", "on"}

_CORRELATION_HEADERS = ("X-Request-ID", "X-Task-ID", "X-Run-ID")
_CORRELATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")


def _correlation_id(value: str | None) -> str:
    """Only allowlisted IDs are logged and echoed; anything else becomes '-'."""
    return value if value and _CORRELATION_ID.fullmatch(value) else ""


def _configured_api_key() -> str:
    return os.getenv(_API_KEY_ENV, "").strip()


def _check_api_key(provided: str | None) -> str:
    """校验 X-API-Key，返回服务端配置的 key（空串表示未开启鉴权）。"""
    expected = _configured_api_key()

    if not expected:
        return ""

    if not provided or not secrets.compare_digest(provided.strip(), expected):
        raise HTTPException(
            status_code=401,
            detail="invalid or missing X-API-Key",
            headers={"WWW-Authenticate": "X-API-Key"},
        )

    return expected


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    return _check_api_key(x_api_key)


def require_ingest_access(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """摄入接口：要么通过 key 鉴权，要么显式开启本地开放摄入。"""
    expected = _check_api_key(x_api_key)

    if expected:
        return expected

    if os.getenv(_ALLOW_INGEST_ENV, "0").strip().lower() not in _TRUTHY:
        raise HTTPException(
            status_code=403,
            detail=(
                "document ingestion is disabled; "
                f"set {_ALLOW_INGEST_ENV}=1 for local use, "
                f"or {_API_KEY_ENV} for authenticated access"
            ),
        )

    return ""


app = FastAPI(
    title="SmartOpsAgent Knowledge Service",
    description="知识库服务：文档摄入 + 混合检索 + 证据生成",
    version="0.1.0",
)

service = KnowledgeService(KnowledgeConfig.from_env())
INSTANCE_ID = uuid4().hex
STARTED_AT = datetime.now(timezone.utc).isoformat()

_REFERENCE_ROOT = Path(__file__).resolve().parent / "reference" / "ops-knowledge-rag"


def _seed_reference_corpus() -> dict:
    """启动时把参考语料写入内存知识库，单个文件失败不影响服务启动。"""
    summary = {"status": "disabled", "documents": 0, "errors": 0, "corpus_sha256": None}
    manifest_path = os.getenv("KNOWLEDGE_CORPUS_MANIFEST")
    if not manifest_path and os.getenv("KNOWLEDGE_SEED_REFERENCE", "1") == "0":
        return summary

    root = Path(
        os.getenv("KNOWLEDGE_REFERENCE_DIR", str(_REFERENCE_ROOT))
    )

    if manifest_path:
        try:
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            documents = verify_snapshot(
                root, manifest,
                expected_version=os.getenv("KNOWLEDGE_CORPUS_VERSION"),
                expected_hash=os.getenv("KNOWLEDGE_CORPUS_SHA256"),
            )
            service.add_documents(documents)
            summary.update(status="verified", documents=len(documents),
                           corpus_sha256=manifest["corpus_sha256"], version=manifest["version"])
        except Exception:
            logger.exception("Corpus manifest validation or ingestion failed")
            summary.update(status="invalid_manifest", errors=1)
        return summary

    if not root.is_dir():
        summary["status"] = "missing"
        logger.warning("参考语料目录不存在，索引需手动摄入")
        return summary

    loaded = 0

    documents = []
    digest = hashlib.sha256()

    for path in sorted(root.rglob("*.md")):
        try:
            content = path.read_text(
                encoding="utf-8",
                errors="ignore",
            )
        except OSError:
            summary["errors"] += 1
            logger.warning(
                "参考语料读取失败：%s",
                path,
                exc_info=True,
            )
            continue

        if not content.strip():
            continue

        documents.append(
            {
                "content": content,
                "source": f"reference/{path.relative_to(root)}",
                "version": "reference",
            }
        )
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8") + b"\0" + content.encode("utf-8") + b"\0")
        loaded += 1

    # 一次性批量摄入，BM25 索引只重建一次。
    service.add_documents(documents)
    summary.update({
        "status": "partial" if summary["errors"] else "loaded" if loaded else "empty",
        "documents": loaded,
        "corpus_sha256": digest.hexdigest() if loaded else None,
    })

    logger.info(
        "参考语料已加载：%s 篇，%s chunks",
        loaded,
        service.chunk_count,
    )
    return summary


SEED_SUMMARY = _seed_reference_corpus()


def _embedding_status() -> dict:
    """RAG-P1-01/02：暴露真实向量后端，避免 BGE 静默回退到 hash 无法察觉。"""
    status = getattr(service.embedding, "backend_status", None)
    if status is None:
        return {"backend_requested": "unknown", "backend_actual": "unknown"}
    return status.to_dict()


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "UP",
        "service": "smartops-knowledge-service",
        "version": "0.1.0",
        "chunks": service.chunk_count,
        "ready": service.chunk_count > 0 and SEED_SUMMARY["status"] != "invalid_manifest",
        "instance_id": INSTANCE_ID,
        "started_at": STARTED_AT,
        "corpus": SEED_SUMMARY,
        "embedding": _embedding_status(),
        "auth_required": bool(_configured_api_key()),
    }


@app.get("/health", include_in_schema=False)
async def health_alias() -> dict:
    """兼容探针的 `/health` 别名，内容与 `/api/health` 一致。"""
    return await health()


@app.get("/api/ready")
async def ready():
    is_ready = service.chunk_count > 0 and SEED_SUMMARY["status"] != "invalid_manifest"
    return JSONResponse(status_code=200 if is_ready else 503, content={
        "status": "READY" if is_ready else "NOT_READY",
        "service": "smartops-knowledge-service",
        "ready": is_ready,
        "reason": "" if is_ready else "invalid_manifest" if SEED_SUMMARY["status"] == "invalid_manifest" else "empty_index",
        "chunks": service.chunk_count,
        "instance_id": INSTANCE_ID,
        "started_at": STARTED_AT,
        "corpus": SEED_SUMMARY,
        "embedding": _embedding_status(),
    })


@app.post("/api/search")
async def search(
    request: SearchRequest,
    response: Response,
    _: str = Depends(require_api_key),
    x_request_id: str | None = Header(default=None, alias="X-Request-ID"),
    x_task_id: str | None = Header(default=None, alias="X-Task-ID"),
    x_run_id: str | None = Header(default=None, alias="X-Run-ID"),
) -> dict:
    correlation = (
        _correlation_id(x_request_id),
        _correlation_id(x_task_id),
        _correlation_id(x_run_id),
    )

    try:
        result = service.search(
            request.query,
            top_k=request.top_k,
            version=request.version,
            source=request.source,
            score_threshold=request.score_threshold,
            vector_weight=request.vector_weight,
            bm25_weight=request.bm25_weight,
        )
    except Exception:
        logger.warning(
            "knowledge.search request_id=%s task_id=%s run_id=%s status=failed",
            correlation[0] or "-", correlation[1] or "-", correlation[2] or "-",
        )
        raise

    logger.info(
        "knowledge.search request_id=%s task_id=%s run_id=%s status=ok results=%s",
        correlation[0] or "-", correlation[1] or "-", correlation[2] or "-",
        len(result.get("results", [])),
    )

    for header, value in zip(_CORRELATION_HEADERS, correlation):
        if value:
            response.headers[header] = value

    return result


@app.post("/api/documents")
async def add_document(
    request: DocumentRequest,
    _: str = Depends(require_ingest_access),
) -> dict:
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
