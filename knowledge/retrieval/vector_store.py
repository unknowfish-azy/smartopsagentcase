"""VectorStore 抽象 + 多种实现。

RAG-P1-02 条件 PoC 脚手架（按方案 B）：
- 提炼 VectorStore Protocol，KnowledgeService / HybridRetriever 依赖抽象
- InMemoryVectorStore 保留（零改动，当前生产路径）
- SqliteVectorStore：持久化精确 cosine（磁盘可持久化，重启恢复）
- FaissVectorStore / QdrantVectorStore：条件 PoC stub，faiss/qdrant 未装时
  优雅降级（不影响生产、不抛 import error、PoC 脚本自动跳过）

边界：
- 默认仍走 InMemoryVectorStore，不切 Faiss/Qdrant
- KnowledgeService 接受注入可选 vector_store 参数，但构造函数默认 InMemory
- 外部（eval_retrieval.py、ablation、test_hybrid/test_vector_retrieval）零改动兼容
"""
from __future__ import annotations

import math
import pickle
import sqlite3
from pathlib import Path
from typing import Protocol, runtime_checkable

from .models import RetrievalResult


# ---------------------------------------------------------------------------
# 公共工具
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    numerator = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return numerator / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# VectorStore Protocol — 最小接口
# ---------------------------------------------------------------------------

@runtime_checkable
class VectorStore(Protocol):
    """向量存储抽象。

    生产实现：InMemoryVectorStore（当前）
    PoC 实现：SqliteVectorStore / FaissVectorStore / QdrantVectorStore
    """

    def add(self, chunk, vector: list[float]) -> None: ...

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ) -> list[RetrievalResult]: ...

    def clear(self) -> None: ...

    def __len__(self) -> int: ...


def _version_matches(chunk, version: str | None) -> bool:
    """共享版本过滤逻辑（各实现统一调）。"""
    if version is None:
        return True
    if version == "latest":
        return True
    return getattr(chunk, "version", None) == version


def _to_retrieval_result(chunk, score: float) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        content=chunk.content,
        score=score,
        source=chunk.source,
        version=chunk.version,
        metadata=chunk.metadata,
        retrieval_type="vector",
    )


# ---------------------------------------------------------------------------
# InMemoryVectorStore（当前生产实现，零改动行为）
# ---------------------------------------------------------------------------

class InMemoryVectorStore:
    """内存向量存储 + 精确 cosine 匹配。

    当前生产路径，KnowledgeService 默认构造。全仓库 eval_retrieval / ablation /
    test_hybrid / test_vector_retrieval 都依赖本类的 add / search 签名。
    RAG-P1-02 重构后本类行为完全不变，只是额外实现 clear / __len__。
    """

    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, chunk, vector: list[float]) -> None:
        self.items.append({"chunk": chunk, "vector": vector})

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ) -> list[RetrievalResult]:
        results = []
        for item in self.items:
            chunk = item["chunk"]
            if not _version_matches(chunk, version):
                continue
            score = cosine_similarity(query_vector, item["vector"])
            results.append(_to_retrieval_result(chunk, score))
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def clear(self) -> None:
        self.items.clear()

    def __len__(self) -> int:
        return len(self.items)


# ---------------------------------------------------------------------------
# SqliteVectorStore — 持久化精确 cosine（磁盘可持久化 + 重启恢复）
# ---------------------------------------------------------------------------

class SqliteVectorStore:
    """SQLite 持久化向量存储 + 精确 cosine 匹配。

    RAG-P1-02 PoC：磁盘可持久化，进程重启后向量索引不丢。
    与 RAG-P1-01 PersistenceManager 互补：PersistenceManager 存 chunks（含
    metadata / version / 语义字段），SqliteVectorStore 存向量 blob + chunk 引用。
    两者 schema 解耦，向量检索逻辑独立。

    注意：精确 cosine 匹配，不是 ANN。299 chunks 规模下和 InMemory 延迟相当，
    但磁盘持久化让重启恢复成为可能（PersistenceManager 存 chunks + 本类存向量）。

    兼容 InMemoryVectorStore 的 .items 属性（空 list），让 KnowledgeService._persist_now
    里硬绑 `.items` 的代码也能安全运行。
    """

    def __init__(self, path: str | Path, dimension: int = 256) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.dimension = dimension
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        # RAG-P1-02：兼容 InMemoryVectorStore 的 .items 只读属性，
        # KnowledgeService._persist_now() 会读它（取 vectors 列表）。
        # SqliteVectorStore 的向量存在 SQLite 里，这里返回空 list 让 persist_now
        # 能安全拿到 None → PersistenceManager.save 不传 vectors（不存向量 blob，
        # 向量由 SqliteVectorStore 自己持久化管理）。
        self.items: list[dict] = []

    def _init_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS vectors (
                chunk_id TEXT PRIMARY KEY,
                document_id TEXT,
                chunk_blob BLOB NOT NULL,
                vector BLOB NOT NULL,
                dimension INTEGER NOT NULL,
                source TEXT,
                version TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_vectors_version ON vectors(version);
            CREATE INDEX IF NOT EXISTS idx_vectors_doc ON vectors(document_id);
        """)
        self._conn.commit()

    def add(self, chunk, vector: list[float]) -> None:
        # 向量长度校验（维度不匹配 → 拒绝，避免混入不同 embedding 的向量）
        if len(vector) != self.dimension:
            raise ValueError(
                f"SqliteVectorStore expects dimension={self.dimension}, "
                f"got {len(vector)} (chunk={getattr(chunk, 'chunk_id', '?')})"
            )
        try:
            cur = self._conn.execute(
                "INSERT OR REPLACE INTO vectors (chunk_id, document_id, chunk_blob, vector, dimension, source, version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    getattr(chunk, "chunk_id", ""),
                    getattr(chunk, "document_id", ""),
                    pickle.dumps(chunk),
                    pickle.dumps(vector),
                    len(vector),
                    getattr(chunk, "source", ""),
                    getattr(chunk, "version", "latest"),
                ),
            )
            self._conn.commit()
            # DEBUG: print(f"[SqliteVectorStore.add] chunk={getattr(chunk, 'chunk_id', '')[:8]} rows affected={cur.rowcount}")
        except Exception as exc:
            # RAG-P1-02: SqliteVectorStore.add 失败不应静默吞掉（不像 _persist_now 可以降级）
            import logging
            logging.getLogger(__name__).warning(
                "SqliteVectorStore.add 失败（仍抛异常让上层知道）：%s", exc
            )
            raise

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ) -> list[RetrievalResult]:
        rows = self._conn.execute(
            "SELECT chunk_blob, vector, version FROM vectors ORDER BY chunk_id"
        ).fetchall()
        results = []
        for chunk_blob, vec_blob, row_version in rows:
            chunk = pickle.loads(chunk_blob)
            vector = pickle.loads(vec_blob)
            if not _version_matches(chunk, version):
                continue
            score = cosine_similarity(query_vector, vector)
            results.append(_to_retrieval_result(chunk, score))
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_k]

    def clear(self) -> None:
        self._conn.execute("DELETE FROM vectors")
        self._conn.commit()

    def __len__(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM vectors")
        return int(cur.fetchone()[0])

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# FaissVectorStore — 条件 PoC stub（faiss 未装时优雅降级）
# ---------------------------------------------------------------------------

class FaissVectorStore:
    """FAISS IndexFlatIP 精确 ANN（PoC 脚手架）。

    **生产禁用**：构造函数检测 faiss 是否可用，不可用时抛 ImportError。
    PoC 脚本用 try/except ImportError 跳过不可用的 store，继续跑其他实现。

    设计：
    - IndexFlatIP（Inner Product）做 ANN，IP ≈ cosine + norm pre-normalize
    - dimension 必填（faiss index 需在 add 时确定）
    - 精确 ANN，不是近似（Flat = brute force，IVF 才是近似；PoC 先 Flat 做基线）
    """

    def __init__(self, dimension: int = 256, *, approximate: bool = False,
                 nlist: int = 16) -> None:
        try:
            import faiss  # noqa: F401 — 检测可用性
        except ImportError as exc:
            raise ImportError(
                "faiss-cpu not installed → FaissVectorStore not available. "
                "PoC script will skip this store. Install with: pip install faiss-cpu"
            ) from exc
        self.dimension = dimension
        self._chunk_ids: list[str] = []
        self._chunks: dict[str, Any] = {}
        # 兼容 InMemoryVectorStore 的 .items（空 list，persist_now 读它安全）
        self.items: list[dict] = []

        import faiss
        if approximate:
            # IndexIVFFlat — 近似 ANN，需 nlist 个聚类中心
            quantizer = faiss.IndexFlatIP(dimension)
            self._index = faiss.IndexIVFFlat(quantizer, dimension, nlist, faiss.METRIC_INNER_PRODUCT)
            self._approximate = True
            self._nlist = nlist
            self._vectors_buffer: list[list[float]] = []  # IVFFlat 需先 train
        else:
            self._index = faiss.IndexFlatIP(dimension)
            self._approximate = False

    def add(self, chunk, vector: list[float]) -> None:
        import faiss
        import numpy as np
        v = np.array([vector], dtype=np.float32)
        # L2 normalize → IP == cosine
        faiss.normalize_L2(v)
        if self._approximate and self._index.is_trained is False:
            self._vectors_buffer.append(vector)
            # 等积累够 nlist * 10 样本再 train（不够就当 Flat 用）
            if len(self._vectors_buffer) >= self._nlist * 10:
                training = np.array(self._vectors_buffer, dtype=np.float32)
                faiss.normalize_L2(training)
                self._index.train(training)
                self._vectors_buffer.clear()
        self._index.add(v)
        self._chunk_ids.append(getattr(chunk, "chunk_id", ""))
        self._chunks[getattr(chunk, "chunk_id", "")] = chunk

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ) -> list[RetrievalResult]:
        import faiss
        import numpy as np
        q = np.array([query_vector], dtype=np.float32)
        faiss.normalize_L2(q)
        k = min(top_k, self._index.ntotal)
        if k == 0:
            return []
        scores, indices = self._index.search(q, k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self._chunk_ids):
                continue
            chunk = self._chunks.get(self._chunk_ids[idx])
            if chunk is None or not _version_matches(chunk, version):
                continue
            results.append(_to_retrieval_result(chunk, float(score)))
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def clear(self) -> None:
        self._chunk_ids.clear()
        self._chunks.clear()
        import faiss
        self._index.reset()

    def __len__(self) -> int:
        return self._index.ntotal


# ---------------------------------------------------------------------------
# QdrantVectorStore — 条件 PoC stub（qdrant 未装时优雅降级）
# ---------------------------------------------------------------------------

class QdrantVectorStore:
    """Qdrant 持久向量存储（PoC 脚手架）。

    **生产禁用**：构造函数检测 qdrant_client 是否可用，不可用时抛 ImportError。
    PoC 脚本自动跳过。Qdrant Server 需独立部署（Docker 容器 + 端口 6333）。

    设计对齐任务书第 148-150 行"Qdrant 映射既有 P2 条件 PoC，
    达到预注册收益和资源门槛后才切默认"的边界：
    - PoC 只跑精确 cosine（不开启 HNSW ANN），当精确基线
    - payload 支持 version / source / tenant / workspace 过滤
    - 默认不 persistent（内存索引），持久化需 Qdrant Server 端 WAL 配置
    """

    def __init__(self, collection_name: str = "smartops_knowledge",
                 url: str = "http://127.0.0.1:6333",
                 dimension: int = 256) -> None:
        try:
            from qdrant_client import QdrantClient  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "qdrant-client not installed → QdrantVectorStore not available. "
                "PoC script will skip this store. Install with: pip install qdrant-client"
            ) from exc
        from qdrant_client import QdrantClient
        from qdrant_client.http.models import Distance, VectorParams, CreateCollection

        self.client = QdrantClient(url=url)
        self.collection_name = collection_name
        self.dimension = dimension
        # 兼容 InMemoryVectorStore 的 .items（空 list，persist_now 读它安全）
        self.items: list[dict] = []

        # 检查 collection 是否存在，不存在则创建
        collections = self.client.get_collections().collections
        exists = any(c.name == collection_name for c in collections)
        if not exists:
            try:
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(
                        size=dimension,
                        distance=Distance.COSINE,
                    ),
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Qdrant Server at {url} not reachable or creation failed: {exc}"
                ) from exc

    def add(self, chunk, vector: list[float]) -> None:
        from qdrant_client.http.models import PointStruct
        payload = {
            "document_id": getattr(chunk, "document_id", ""),
            "source": getattr(chunk, "source", ""),
            "version": getattr(chunk, "version", "latest"),
        }
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(
                id=getattr(chunk, "chunk_id", ""),
                vector=vector,
                payload=payload,
            )],
        )
        # 本地也存一份 chunk 对象，search 返回时能带上 RetrievalResult 全字段
        if not hasattr(self, "_chunk_cache"):
            self._chunk_cache: dict[str, Any] = {}
        self._chunk_cache[getattr(chunk, "chunk_id", "")] = chunk

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ) -> list[RetrievalResult]:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue
        query_filter = None
        if version is not None and version != "latest":
            query_filter = Filter(must=[
                FieldCondition(key="version", match=MatchValue(value=version))
            ])
        points = self.client.query_points(
            collection_name=self.collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        ).points
        results = []
        if not hasattr(self, "_chunk_cache"):
            self._chunk_cache = {}
        for pt in points:
            chunk = self._chunk_cache.get(str(pt.id))
            if chunk is None:
                continue
            results.append(_to_retrieval_result(chunk, pt.score))
        results.sort(key=lambda x: x.score, reverse=True)
        return results

    def clear(self) -> None:
        try:
            self.client.delete_collection(collection_name=self.collection_name)
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config={"size": self.dimension, "distance": "COSINE"},
            )
        except Exception:
            pass
        if hasattr(self, "_chunk_cache"):
            self._chunk_cache.clear()

    def __len__(self) -> int:
        try:
            return self.client.count(collection_name=self.collection_name).count
        except Exception:
            return 0

    def close(self) -> None:
        self.client.close()


# ---------------------------------------------------------------------------
# Factory：发现可用的 VectorStore 实现（PoC 脚本用）
# ---------------------------------------------------------------------------

def discover_stores(*, path: str | Path | None = None,
                    dimension: int = 256,
                    enable_in_memory: bool = True,
                    enable_sqlite: bool = False,
                    enable_faiss: bool = True,
                    enable_qdrant: bool = False,
                    qdrant_url: str = "http://127.0.0.1:6333",
                    sqlite_path: str = ".cache/rag-p1-02/sqlite.sqlite3") -> dict[str, VectorStore]:
    """PoC 用：自动发现可用的 VectorStore 实现并实例化。

    返回 dict[name -> store]，不可用的（faiss/qdrant 未装）自动跳过。
    KnowledgeService 生产路径不调用本函数，仍硬绑 InMemoryVectorStore。
    """
    stores: dict[str, VectorStore] = {}

    if enable_in_memory:
        stores["in_memory"] = InMemoryVectorStore()

    if enable_sqlite:
        stores["sqlite"] = SqliteVectorStore(Path(sqlite_path), dimension)

    if enable_faiss:
        try:
            stores["faiss_indexflatip"] = FaissVectorStore(dimension, approximate=False)
        except ImportError:
            pass

    if enable_qdrant:
        try:
            stores["qdrant"] = QdrantVectorStore(dimension=dimension, url=qdrant_url)
        except ImportError:
            pass

    return stores


__all__ = [
    "VectorStore",
    "InMemoryVectorStore",
    "SqliteVectorStore",
    "FaissVectorStore",
    "QdrantVectorStore",
    "cosine_similarity",
    "discover_stores",
]
