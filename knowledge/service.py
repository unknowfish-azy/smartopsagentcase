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

from typing import Any
from uuid import uuid4

from knowledge.config import DEFAULT_CONFIG, KnowledgeConfig
from knowledge.embedding.hash_embedding import HashEmbedding
from knowledge.evidence.citation import build_citations, build_evidence
from knowledge.evidence.trust_score import TrustScoreCalculator
from knowledge.ingestion.chunker import TextChunker
from knowledge.reranker.lexical_reranker import LexicalReranker
from knowledge.retrieval.bm25 import BM25Retriever
from knowledge.retrieval.hybrid import HybridRetriever
from knowledge.retrieval.vector_store import InMemoryVectorStore


class KnowledgeService:
    """
    知识库服务，负责文档摄入与混合检索。

    当前为内存实现，不依赖外部向量数据库，适合开发与演示。
    """

    def __init__(
        self,
        config: KnowledgeConfig | None = None,
    ) -> None:
        self.config = config or DEFAULT_CONFIG

        self.embedding = HashEmbedding()

        self.chunker = TextChunker(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap,
        )

        self.vector_store = InMemoryVectorStore()

        self.reranker = LexicalReranker()

        self.trust_calculator = TrustScoreCalculator()

        self._chunks = []

        self._bm25 = BM25Retriever([])

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
        document_id = document_id or str(uuid4())

        chunks = self.chunker.split(
            document_id,
            content,
            source=source,
            version=version,
        )

        vectors = self.embedding.encode(
            [chunk.content for chunk in chunks]
        )

        for chunk, vector in zip(chunks, vectors):
            self.vector_store.add(chunk, vector)
            self._chunks.append(chunk)

        self._rebuild_bm25()

        return len(chunks)

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
    ) -> dict[str, Any]:
        """
        混合检索并生成证据、引用和可信度。
        """
        query_vector = self.embedding.encode([query])[0]

        hybrid = HybridRetriever(
            self.vector_store,
            self._bm25,
            vector_weight=self.config.vector_weight,
            bm25_weight=self.config.bm25_weight,
        )

        results = hybrid.search(
            query=query,
            query_vector=query_vector,
            top_k=self.config.top_k_hybrid,
            version=version,
        )

        results = self.reranker.rerank(
            query,
            results,
            top_k=top_k,
        )

        evidences = build_evidence(results)

        citations = build_citations(evidences)

        trust_score = self.trust_calculator.calculate(
            evidences,
            answer_supported=bool(results),
        )

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
            "trust_score": trust_score,
        }

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
