"""RAG-P1-01：工厂增强 + 持久化 + backend_status 测试。"""
import os
import tempfile
from pathlib import Path

from knowledge.embedding.factory import create_embedding, EmbeddingModelWithStatus
from knowledge.embedding.backend_status import EmbeddingBackendStatus, PersistenceManifest
from knowledge.embedding.persistence import PersistenceManager, compute_corpus_sha
from knowledge.service import KnowledgeService
from knowledge.ingestion.chunker import TextChunker


# ---------------------------------------------------------------------------
# RAG1：EmbeddingBackendStatus
# ---------------------------------------------------------------------------

def test_hash_backend_status_is_structured():
    emb = create_embedding("hash")
    assert isinstance(emb, EmbeddingModelWithStatus)
    s = emb.backend_status
    assert isinstance(s, EmbeddingBackendStatus)
    assert s.backend_requested == "hash"
    assert s.backend_actual == "hash"
    assert s.dimension == 256
    assert s.has_fallback is False
    assert s.fallback_reason is None

def test_unknown_backend_falls_back_and_marks_status():
    emb = create_embedding("not-a-real-backend")
    s = emb.backend_status
    assert s.backend_requested == "not-a-real-backend"
    assert s.backend_actual == "hash"
    assert s.has_fallback is True
    assert s.fallback_reason is not None
    assert "未知后端" in s.fallback_reason

def test_status_to_dict_roundtrip():
    s = EmbeddingBackendStatus(
        backend_requested="bge", backend_actual="hash",
        fallback_reason="模型不可用", dimension=256,
    )
    d = s.to_dict()
    assert d["backend_requested"] == "bge"
    assert d["backend_actual"] == "hash"
    assert d["has_fallback"] is True
    # JSON roundtrip 不崩
    import json
    json.loads(s.to_json())


# ---------------------------------------------------------------------------
# RAG2：持久化 save / load / manifest / corpus_sha
# ---------------------------------------------------------------------------

def test_persistence_save_and_load(tmp_path):
    db = PersistenceManager(tmp_path / "rag.sqlite3")
    chunker = TextChunker(chunk_size=100, chunk_overlap=0)
    # split 会自动填 chunk_index（必需字段）
    chunks = chunker.split("d1", "nginx reload 测试内容 config update reload systemctl restart",
                           source="test", version="v1")

    manifest = PersistenceManifest(
        corpus_sha=compute_corpus_sha(chunks),
        corpus_chunks=len(chunks),
        embedding_backend="hash",
        dimension=256,
    )
    db.save(chunks, manifest)
    assert db.count() == len(chunks)

    # 用全新 PersistenceManager 读取（模拟进程重启）
    db2 = PersistenceManager(tmp_path / "rag.sqlite3")
    loaded, loaded_manifest = db2.load()
    assert len(loaded) == len(chunks)
    # chunk_index 被保留
    for orig, got in zip(chunks, loaded):
        assert orig.chunk_index == got.chunk_index
        assert orig.content == got.content
    assert loaded_manifest is not None
    assert loaded_manifest.corpus_sha == manifest.corpus_sha
    assert loaded_manifest.embedding_backend == "hash"
    assert loaded_manifest.dimension == 256

def test_knowledge_service_persist_roundtrip(tmp_path):
    """KnowledgeService 带 persist_path → add_documents 后自动持久化，
    第二次创建 KnowledgeService + persist_path → 自动恢复。
    """
    persist_path = tmp_path / "rag_index.sqlite3"

    # 第一实例：摄入并持久化
    svc1 = KnowledgeService(persist_path=str(persist_path))
    svc1.add_document("nginx reload 配置更新测试", source="test/ref", version="v1")
    assert svc1.chunk_count > 0

    # 第二实例（模拟重启）：自动恢复
    svc2 = KnowledgeService(persist_path=str(persist_path))
    # 恢复应该把 chunks 从持久化载入了
    assert svc2.chunk_count == svc1.chunk_count

    # 第二实例可以直接 search（不需要重新摄入）
    result = svc2.search("nginx reload")
    assert result["query"] == "nginx reload"
    # 返回 dict 应有 RAG-P1-01 新增字段
    assert "version_policy" in result
    assert "filter_applied" in result

def test_compute_corpus_sha_is_deterministic():
    """同一 chunks 序列 → corpus_sha 恒定（frozen snapshot 复现）。"""
    chunker = TextChunker(chunk_size=100, chunk_overlap=0)
    c1 = chunker.split("d1", "hello world", source="a", version="v1")
    c2 = chunker.split("d1", "hello world", source="a", version="v1")
    assert compute_corpus_sha(c1) == compute_corpus_sha(c2)

def test_compute_corpus_sha_changes_with_content():
    chunker = TextChunker(chunk_size=100, chunk_overlap=0)
    c1 = chunker.split("d1", "hello world", source="a", version="v1")
    c2 = chunker.split("d1", "hello different world", source="a", version="v1")
    assert compute_corpus_sha(c1) != compute_corpus_sha(c2)


# ---------------------------------------------------------------------------
# RAG-P1-01：KnowledgeService.search 带 RAG-P1-01 新增字段
# ---------------------------------------------------------------------------

def test_search_returns_backend_status_fields(tmp_path):
    svc = KnowledgeService(persist_path=str(tmp_path / "rag.sqlite3"))
    svc.add_document("nginx reload 配置更新测试", source="test/ref", version="v1")
    result = svc.search("nginx reload")
    # VERSION-P0-01 新增字段
    assert "version_policy" in result
    assert "insufficient" in result
    assert "filter_applied" in result
    # backend_status 挂在 embedding 上
    emb_status = svc.embedding.backend_status
    assert emb_status.backend_actual in ("hash", "bge")
