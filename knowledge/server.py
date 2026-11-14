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

访问控制（SEC-12，默认 fail-closed）：

    KNOWLEDGE_API_KEY=<key>              开启鉴权，检索/摄入需带 X-API-Key（生产必须配置）
    KNOWLEDGE_ALLOW_ANONYMOUS=true       未配置 key 时显式允许匿名访问（仅限本机回环客户端；
                                          即便进程绑定 0.0.0.0，非回环来源的匿名请求也会被拒绝）
    KNOWLEDGE_ALLOW_INGEST=1             兼容保留：摄入永不接受匿名（必须配置 API KEY），
                                          未配置 key 时该开关不再放行任何摄入
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

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
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
# 访问控制（SEC-12）
#
#   KNOWLEDGE_API_KEY       设置后，检索与摄入都必须携带 X-API-Key 头。
#   KNOWLEDGE_ALLOW_ANONYMOUS
#                           未设置 key 时的显式逃生口：仅允许本机回环客户端匿名访问
#                           （应用层强制，与进程绑定地址无关）。
#   KNOWLEDGE_ALLOW_INGEST  兼容保留：摄入永不接受匿名，未配置 key 时一律 403。
# ----------------------------------------------------------------------

_API_KEY_ENV = "KNOWLEDGE_API_KEY"
_ALLOW_INGEST_ENV = "KNOWLEDGE_ALLOW_INGEST"
_ALLOW_ANONYMOUS_ENV = "KNOWLEDGE_ALLOW_ANONYMOUS"
_TRUTHY = {"1", "true", "yes", "on"}
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

_CORRELATION_HEADERS = ("X-Request-ID", "X-Task-ID", "X-Run-ID")
_CORRELATION_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")


def _correlation_id(value: str | None) -> str:
    """Only allowlisted IDs are logged and echoed; anything else becomes '-'."""
    return value if value and _CORRELATION_ID.fullmatch(value) else ""


def _configured_api_key() -> str:
    return os.getenv(_API_KEY_ENV, "").strip()


def _anonymous_allowed() -> bool:
    return os.getenv(_ALLOW_ANONYMOUS_ENV, "").strip().lower() in _TRUTHY


def _is_loopback(request: Request) -> bool:
    client = request.client
    return bool(client and client.host in _LOOPBACK_HOSTS)


def _check_api_key(provided: str | None, request: Request) -> str:
    """校验 X-API-Key，返回服务端配置的 key（空串表示匿名放行）。"""
    expected = _configured_api_key()

    if expected:
        if not provided or not secrets.compare_digest(provided.strip(), expected):
            raise HTTPException(
                status_code=401,
                detail="invalid or missing X-API-Key",
                headers={"WWW-Authenticate": "X-API-Key"},
            )
        return expected

    # SEC-12：未配置 key 时默认 fail-closed。唯一的逃生口是显式开启匿名模式，
    # 且匿名只对本机回环客户端放行（应用层强制，不依赖绑定地址）。
    if not _anonymous_allowed():
        logger.error(
            "KNOWLEDGE_API_KEY is not configured and anonymous access is not "
            "explicitly enabled; refusing unauthenticated requests (fail-closed). "
            "Set KNOWLEDGE_API_KEY, or set KNOWLEDGE_ALLOW_ANONYMOUS=true for "
            "loopback-only local use."
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "knowledge service auth is not configured; "
                f"set {_API_KEY_ENV} (recommended) or {_ALLOW_ANONYMOUS_ENV}=true "
                "for loopback-only local use"
            ),
        )

    if not _is_loopback(request):
        raise HTTPException(
            status_code=403,
            detail="anonymous access is restricted to loopback clients; configure an API key",
        )

    return ""


def require_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    return _check_api_key(x_api_key, request)


def require_ingest_access(
    request: Request,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> str:
    """摄入接口：SEC-12 后必须携带有效 API KEY，永不接受匿名（含 ALLOW_INGEST 兜底）。"""
    expected = _configured_api_key()
    if not expected:
        raise HTTPException(
            status_code=403,
            detail=(
                "document ingestion requires an API key; anonymous ingestion is "
                f"permanently disabled (set {_API_KEY_ENV})"
            ),
        )
    return _check_api_key(x_api_key, request)


app = FastAPI(
    title="SmartOpsAgent Knowledge Service",
    description="知识库服务：文档摄入 + 混合检索 + 证据生成",
    version="0.1.0",
)

service = KnowledgeService(KnowledgeConfig.from_env())
INSTANCE_ID = uuid4().hex
STARTED_AT = datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
async def _assert_auth_configured() -> None:
    """SEC-12：未配置 key 且未显式允许匿名（仅回环）时拒绝启动（fail-closed）。"""
    if not _configured_api_key() and not _anonymous_allowed():
        raise RuntimeError(
            "KNOWLEDGE_API_KEY is not configured and anonymous access is not "
            "explicitly enabled; refusing to start (fail-closed). Set "
            "KNOWLEDGE_API_KEY for authenticated deployments, or "
            "KNOWLEDGE_ALLOW_ANONYMOUS=true for loopback-only local use."
        )
    if not _configured_api_key():
        logger.warning(
            "KNOWLEDGE_ALLOW_ANONYMOUS=true: anonymous access is restricted to "
            "loopback clients at the application layer; do not expose this "
            "process to other hosts without an API key."
        )

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


# ---------------------------------------------------------------------------
# Spatial Field Phase B：catalog.json ingest（启动时）
# ---------------------------------------------------------------------------

# catalog.json 位置：backend resources（Phase A knowledge:export 产出）
_CATALOG_PATH_DEFAULT = (
    Path(__file__).resolve().parents[2]
    / "backend" / "src" / "main" / "resources"
    / "knowledge" / "catalog.json"
)


def _seed_catalog_snapshot() -> dict:
    """启动时把 catalog.json（前端 737 条 knowledgeEntries 快照）ingest 进服务。

    关键：document_id 强制 = entry.id，保证 KnowledgeService chunk 与前端
    knowledgeEntry 连接键硬对齐（Phase B HC-1）。

    失败降级：返回空 summary，不影响服务启动（Phase B HC-4）。
    """
    summary = {
        "status": "disabled",
        "entries": 0,
        "documents": 0,
        "chunks": 0,
        "errors": 0,
    }
    if os.getenv("KNOWLEDGE_AUTO_INGEST_CATALOG", "1") == "0":
        summary["status"] = "disabled_by_env"
        return summary

    catalog_path = Path(
        os.getenv("KNOWLEDGE_CATALOG_PATH", str(_CATALOG_PATH_DEFAULT))
    )
    if not catalog_path.is_file():
        summary["status"] = "missing"
        logger.info(
            "catalog.json 不存在（跳过 ingest_catalog）：%s", catalog_path
        )
        return summary

    try:
        n_chunks = service.ingest_catalog(catalog_path)
        summary["entries"] = n_chunks  # entries → documents → chunks 三步
        summary["chunks"] = n_chunks
        summary["documents"] = service.chunk_count - SEED_SUMMARY.get("documents", 0)
        summary["status"] = "ingested" if n_chunks > 0 else "empty"
        logger.info(
            "[spatial-field] catalog.json ingest 完成：%s chunks, 总计 %s chunks",
            n_chunks, service.chunk_count,
        )
    except Exception:
        logger.exception("catalog.json ingest 失败（不影响服务）")
        summary["status"] = "error"
        summary["errors"] = 1

    return summary


CATALOG_SUMMARY = _seed_catalog_snapshot()


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
        "auth_mode": _auth_mode(),
    }


def _auth_mode() -> str:
    if _configured_api_key():
        return "api_key"
    if _anonymous_allowed():
        return "anonymous_loopback_only"
    return "misconfigured_fail_closed"


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
        "catalog": CATALOG_SUMMARY,
        "embedding": _embedding_status(),
    })


# ---------------------------------------------------------------------------
# Spatial Field Phase B：chunk 查询端点（只读，Pydantic 契约）
# ---------------------------------------------------------------------------

class ChunkRef(BaseModel):
    chunkId: str
    documentId: str
    content: str
    chunkIndex: int = 0
    source: str = ""
    version: str = "latest"
    metadata: dict = {}


class ChunkListResponse(BaseModel):
    entryId: str
    documentId: str
    chunks: list[ChunkRef]
    count: int


class EvidenceRefOut(BaseModel):
    evidenceId: str
    chunkId: str
    source: str
    version: str
    capturedAt: str = ""
    note: str = ""


class EvidenceRefsResponse(BaseModel):
    entryId: str
    evidenceRefs: list[EvidenceRefOut]
    source: str  # "ingested-from-catalog" | "not-ingested"
    ingestedAt: str


@app.get(
    "/api/knowledge/{entry_id}/chunks",
    response_model=ChunkListResponse,
    summary="只读：按 knowledgeEntry.id 返回已 ingest 的 chunks",
)
async def get_entry_chunks(entry_id: str) -> ChunkListResponse:
    """Phase B 只读端点：返回 catalog ingest 后某个 knowledgeEntry 对应的全部 chunks。

    不引入新表，运行时从内存索引过滤。未 ingest 时返回空 list（不报错）。
    """
    chunks = service.find_chunks_for_document(entry_id)
    chunk_refs = [
        ChunkRef(
            chunkId=c.chunk_id,
            documentId=getattr(c, "document_id", entry_id),
            content=c.content,
            chunkIndex=getattr(c, "chunk_index", 0),
            source=getattr(c, "source", ""),
            version=getattr(c, "version", "latest"),
            metadata=dict(getattr(c, "metadata", {}) or {}),
        )
        for c in chunks
    ]
    return ChunkListResponse(
        entryId=entry_id,
        documentId=entry_id,  # catalog.json ingest 强制 document_id = entry_id
        chunks=chunk_refs,
        count=len(chunk_refs),
    )


@app.get(
    "/api/knowledge/{entry_id}/evidence-refs",
    response_model=EvidenceRefsResponse,
    summary="只读：按 knowledgeEntry.id 返回 EvidenceRef 列表",
)
async def get_entry_evidence_refs(entry_id: str) -> EvidenceRefsResponse:
    """Phase B 只读端点：把 chunks 拼装成 EvidenceRef 格式返回给前端。

    设计（KNOWLEDGE-INSIGHT-BINDING.md §2.1 的 EvidenceRef）：
      evidenceId = "ev-<chunk_id>"（稳定可追溯）
      capturedAt = ingested_at（启动 ingest 的时间戳）
      note = "知识条目原始内容切块后直接作为证据锚点"

    未 ingest 时返回空 list（不报错），让前端渲染为 Phase A 真实状态。
    """
    chunks = service.find_chunks_for_document(entry_id)
    ingested_at = STARTED_AT  # 模块级启动时间（catalog ingest 即启动时）
    source_label = (
        "ingested-from-catalog" if chunks else "not-ingested"
    )
    refs = [
        EvidenceRefOut(
            evidenceId=f"ev-{c.chunk_id}",
            chunkId=c.chunk_id,
            source=getattr(c, "source", ""),
            version=getattr(c, "version", "latest"),
            capturedAt=ingested_at,
            note="知识条目原始内容切块后直接作为证据锚点",
        )
        for c in chunks
    ]
    return EvidenceRefsResponse(
        entryId=entry_id,
        evidenceRefs=refs,
        source=source_label,
        ingestedAt=ingested_at,
    )


@app.get(
    "/api/knowledge/index-stats",
    summary="只读：catalog ingest 状态 + 已对齐的 document_id 数",
)
async def get_index_stats() -> dict:
    """Phase B HUD 辅助端点：让前端看到 catalog ingest 是否完成、对齐了多少 entry。"""
    return {
        "catalog": CATALOG_SUMMARY,
        "reference": SEED_SUMMARY,
        "chunks_total": service.chunk_count,
        "document_ids_total": len(service.document_ids()),
    }


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
