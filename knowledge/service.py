"""
SmartOpsAgent Knowledge Service.

统一知识库服务：

    Document
        ↓
    Chunker（切块）
        ↓
    Embedding（向量化）
        ↓
    VectorStore + BM25
        ↓
    Hybrid Retriever（混合检索）
        ↓
    Lexical Reranker（重排序）
        ↓
    Evidence / Citation / Trust Score
"""

from __future__ import annotations

import threading
from typing import Any, Iterable
from uuid import uuid4

from knowledge.config import DEFAULT_CONFIG, KnowledgeConfig
from knowledge.embedding.base import EmbeddingModel
from knowledge.embedding.factory import create_embedding
from knowledge.evidence.citation import build_citations, build_evidence
from knowledge.evidence.trust_score import L3JudgeConfig, TrustScoreCalculator
from knowledge.ingestion.chunker import TextChunker
from knowledge.reranker.lexical_reranker import LexicalReranker
from knowledge.retrieval.bm25 import BM25Retriever
from knowledge.retrieval.hybrid import HybridRetriever
from knowledge.retrieval.vector_store import (
    InMemoryVectorStore,
    VectorStore,
)
from knowledge.retrieval.version_filter import (
    VersionFilter,
    VersionPolicy,
    Version,
    LatestResolutionLedger,
    build_filter,
)
from knowledge.embedding.backend_status import PersistenceManifest
from knowledge.embedding.persistence import PersistenceManager, compute_corpus_sha


class KnowledgeService:
    """
    知识库服务，负责文档摄入与混合检索。

    当前为内存实现，不依赖外部向量数据库，适合开发与演示。
    """

    def __init__(
        self,
        config: KnowledgeConfig | None = None,
        *,
        embedding: EmbeddingModel | None = None,
        vector_store: VectorStore | None = None,
        persist_path: str | Path | None = None,
    ) -> None:
        self.config = config or DEFAULT_CONFIG

        # RAG-P1-02：vector_store 注入用 is not None 显式检查，不用 or。
        # 原因：有 __len__ 的 VectorStore 实例（SqliteVectorStore/FaissVectorStore/QdrantVectorStore）
        # 在空状态下 len=0 → bool=False → or 会错误地用默认值覆盖注入的 store。
        self.vector_store = vector_store if vector_store is not None else InMemoryVectorStore()

        # 允许注入向量后端（评测时同一份语料跑 hash / bge 对比）。
        self.embedding = embedding or create_embedding(
            self.config.embedding_backend,
            self.config.embedding_model,
            self.config.vector_cache_path,
        )

        self.chunker = TextChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )

        self.reranker = LexicalReranker()

        # TRUST-L3-P1-01：L3 judge 默认 passthrough（config.l3_judge_enabled=False），
        # 关闭时零模型调用；judge 可注入，未注入时即使是 enabled 也走 passthrough。
        self.trust_calculator = TrustScoreCalculator(
            l3_config=L3JudgeConfig(
                enabled=bool(getattr(self.config, "l3_judge_enabled", False)),
                timeout_ms=int(getattr(self.config, "l3_judge_timeout_ms", 800)),
                min_confidence=float(
                    getattr(self.config, "l3_judge_min_confidence", 0.6)
                ),
            )
        )

        self._chunks = []

        self._bm25 = BM25Retriever([])

        # 摄入与检索共享同一份内存索引，用可重入锁保证并发安全。
        self._lock = threading.RLock()

        # VERSION-P0-01：latest 解析记账 + 版本/ACL 统一过滤
        self._latest_ledger = LatestResolutionLedger()
        self._corpus_sha: str | None = None
        self._tenant_id: str | None = None
        self._workspace_id: str | None = None

        # RAG-P1-01：持久化管理器（可选）
        self._persistence: PersistenceManager | None = None
        self._persist_path: str | None = None
        if persist_path is not None:
            self._persistence = PersistenceManager(persist_path)
            self._persist_path = str(persist_path)
            # 启动时尝试从持久化恢复
            self._try_load_from_persistence()

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def add_document(
        self,
        content: str,
        *,
        source: str = "",
        version: str = "latest",
        document_id: str | None = None,
    ) -> int:
        """
        摄入一篇文档，返回切分出的 chunk 数量。
        """
        return self.add_documents(
            [
                {
                    "content": content,
                    "source": source,
                    "version": version,
                    "document_id": document_id,
                }
            ]
        )

    def add_documents(
        self,
        documents: Iterable[dict[str, Any]],
    ) -> int:
        """
        批量摄入文档，返回切分出的 chunk 总数。

        BM25 索引只在整批写入完成后重建一次，
        避免逐篇摄入时反复重建导致的启动耗时放大。
        """
        prepared: list[tuple[str, str, str, str]] = []

        for document in documents:
            content = document.get("content") or ""

            if not content.strip():
                continue

            prepared.append(
                (
                    content,
                    document.get("source") or "",
                    document.get("version") or "latest",
                    document.get("document_id") or str(uuid4()),
                )
            )

        if not prepared:
            return 0

        chunks = []

        for content, source, version, document_id in prepared:
            chunks.extend(
                self.chunker.split(
                    document_id,
                    content,
                    source=source,
                    version=version,
                )
            )

        vectors = self.embedding.encode(
            [chunk.content for chunk in chunks]
        )

        with self._lock:
            for chunk, vector in zip(chunks, vectors):
                self.vector_store.add(chunk, vector)
                self._chunks.append(chunk)

            self._rebuild_bm25()

        # RAG-P1-01：持久化（若启用）
        self._persist_now()

        return len(chunks)

    # ------------------------------------------------------------------
    # RAG-P1-01：持久化 / 恢复
    # ------------------------------------------------------------------

    def _persist_now(self) -> None:
        """当前 chunks 写入持久化层（可选）。"""
        if self._persistence is None:
            return
        try:
            manifest = PersistenceManifest(
                corpus_sha=compute_corpus_sha(self._chunks),
                corpus_docs=len(set(
                    getattr(c, "document_id", "") for c in self._chunks
                )),
                corpus_chunks=len(self._chunks),
                embedding_backend=getattr(self.embedding, "backend_status", None).backend_actual
                    if getattr(self.embedding, "backend_status", None) else "hash",
                model_revision=getattr(self.embedding, "backend_status", None).model_revision
                    if getattr(self.embedding, "backend_status", None) else None,
                dimension=getattr(self.embedding, "backend_status", None).dimension
                    or self.embedding.dimension(),
            )
            self._corpus_sha = manifest.corpus_sha
            vectors = [
                item["vector"] for item in self.vector_store.items
            ] if self.vector_store else None
            self._persistence.save(self._chunks, manifest, vectors=vectors)
        except Exception as exc:
            # 持久化失败不能影响服务运行（内存索引照样工作）
            import logging
            logging.getLogger(__name__).warning(
                "RAG-P1-01 持久化失败（不影响服务）：%s", exc
            )

    def _try_load_from_persistence(self) -> None:
        """启动时从持久化层恢复（可选）。"""
        if self._persistence is None:
            return
        try:
            chunks, manifest = self._persistence.load()
            if not chunks:
                return
            vectors = self.embedding.encode(
                [c.content for c in chunks]
            )
            with self._lock:
                for chunk, vector in zip(chunks, vectors):
                    self.vector_store.add(chunk, vector)
                    self._chunks.append(chunk)
                self._rebuild_bm25()
            if manifest:
                self._corpus_sha = manifest.corpus_sha
                # 若持久化的 manifest 的 embedding_backend 和当前请求的不同 → 警告
                actual_backend = getattr(self.embedding, "backend_status", None).backend_actual or "hash"
                if manifest.embedding_backend != actual_backend:
                    import logging
                    logging.getLogger(__name__).warning(
                        "持久化索引 embedding_backend=%s，但当前请求=%s（维度/分词可能不同）",
                        manifest.embedding_backend, actual_backend,
                    )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning(
                "从持久化恢复失败（不影响服务）：%s", exc
            )

    def _rebuild_bm25(self) -> None:
        self._bm25 = BM25Retriever(self._chunks)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        version: str | None = None,
        source: str | None = None,
        score_threshold: float | None = None,
        vector_weight: float | None = None,
        bm25_weight: float | None = None,
        tenant_id: str | None = None,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """
        混合检索并生成证据、引用和可信度。

        VERSION-P0-01 重构：版本 + tenant/workspace/ACL 过滤统一在本方法应用，
        而不是各 retriever 自实现（bm25.py 已移除内联版本过滤）。

        所有可选过滤/权重参数默认 ``None``，保持向后兼容。新增参数 tenant_id /
        workspace_id 为任务书 VERSION-P0-01 要求的 ACL 过滤入口，当前骨架实现
        （真实 identity provider 接入后再填充完整 tenant/workspace 字段）。

        返回 dict 新增字段：``version_policy`` / ``insufficient`` / ``filter_applied``
        让调用方能看到版本策略 + INSUFFICIENT 标记 + 过滤是否实际生效。
        """
        effective_vector_weight = (
            vector_weight if vector_weight is not None else self.config.vector_weight
        )
        effective_bm25_weight = (
            bm25_weight if bm25_weight is not None else self.config.bm25_weight
        )

        query_vector = self.embedding.encode(
            [query],
            is_query=True,
        )[0]

        # 读取索引期间持锁，避免与批量摄入的写入过程交错。
        with self._lock:
            hybrid = HybridRetriever(
                self.vector_store,
                self._bm25,
                vector_weight=effective_vector_weight,
                bm25_weight=effective_bm25_weight,
            )

            # VERSION-P0-01：hybrid 不再做版本过滤，由 VersionFilter 统一应用
            results = hybrid.search(
                query=query,
                query_vector=query_vector,
                top_k=self.config.top_k_hybrid,
                version=version,  # 签名兼容，hybrid 不再消费
            )

        # VERSION-P0-01：版本 + tenant/workspace/ACL 统一过滤
        filter_ctx = {
            "tenant_id": tenant_id or self._tenant_id,
            "workspace_id": workspace_id or self._workspace_id,
        }
        version_filter = build_filter(
            expected_version=version,
            corpus_sha=self._corpus_sha,
            latest_ledger=self._latest_ledger,
            filter_context=filter_ctx,
        )
        results = version_filter.filter(results)

        # 截断低分给源：阈值由调用方决定，不传则不过滤。
        if score_threshold is not None:
            results = [
                result
                for result in results
                if result.score >= score_threshold
            ]

        if source:
            results = [
                result
                for result in results
                if source in (result.source or "")
            ]

        results = self.reranker.rerank(
            query,
            results,
            top_k=top_k,
        )

        evidences = build_evidence(results)

        citations = build_citations(evidences)

        trust = self.trust_calculator.breakdown(evidences)

        return {
            "query": query,
            "results": [
                self._result_to_dict(result)
                for result in results
            ],
            "evidences": [
                self._evidence_to_dict(evidence)
                for evidence in evidences
            ],
            "citations": citations,
            "trust_score": trust.trust_score,
            # TRUST-L3-P1-01: 四个维度分开暴露；trust_score 仍是版本化启发式分，
            # 不是正确概率（interpretation 字段显式声明）。
            "trust": trust.to_dict(),
            # VERSION-P0-01 新增：下游证据引用可看到过滤状态
            "version_policy": version_filter.policy.value,
            "insufficient": version_filter.insufficient,
            "filter_applied": True,
            "filter_context": filter_ctx,
            "latest_ledger_size": len(self._latest_ledger),
        }

    # ------------------------------------------------------------------
    # VERSION-P0-01：接入点（server.py 调用 _seed_reference_corpus 后填充）
    # ------------------------------------------------------------------

    def set_corpus_state(self, *, corpus_sha: str | None = None,
                         tenant_id: str | None = None,
                         workspace_id: str | None = None) -> None:
        """外部（server.py 启动脚本）注入 corpus_sha + tenant/workspace 默认值。

        VERSION-P0-01：VersionPolicy 解析 latest 时需要知道"当前 corpus 是什么版本"，
        以决定 latest 解析结果是否与 corpus 对齐；tenant/workspace 默认值用于 filter_context。
        """
        if corpus_sha is not None:
            self._corpus_sha = corpus_sha
        if tenant_id is not None:
            self._tenant_id = tenant_id
        if workspace_id is not None:
            self._workspace_id = workspace_id

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _result_to_dict(result) -> dict[str, Any]:
        return {
            "chunk_id": result.chunk_id,
            "document_id": result.document_id,
            "content": result.content,
            "source": result.source,
            "version": result.version,
            "score": result.score,
            "retrieval_type": result.retrieval_type,
        }

    @staticmethod
    def _evidence_to_dict(evidence) -> dict[str, Any]:
        return {
            "evidence_id": evidence.evidence_id,
            "chunk_id": evidence.chunk_id,
            "source": evidence.source,
            "content": evidence.content,
            "score": evidence.score,
            "version": evidence.version,
        }

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)


__all__ = [
    "KnowledgeService",
]
