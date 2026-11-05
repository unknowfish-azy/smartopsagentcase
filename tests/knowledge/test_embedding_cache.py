"""向量缓存与后端工厂行为的单元测试。"""

from knowledge.embedding.base import EmbeddingModel
from knowledge.embedding.cache import SqliteVectorCache, cache_key
from knowledge.embedding.caching import CachedEmbedding
from knowledge.embedding.factory import create_embedding
from knowledge.embedding.hash_embedding import HashEmbedding


class _CountingEmbedding(EmbeddingModel):
    """记录真实推理调用次数，用于验证缓存是否命中。"""

    def __init__(self) -> None:
        self.calls = 0

    def dimension(self) -> int:
        return 4

    def encode(self, texts, *, is_query=False):
        self.calls += len(texts)
        return [[float(len(text) % 7), 1.0, 2.0, 3.0] for text in texts]


def test_cache_hit_skips_model_inference(tmp_path):
    inner = _CountingEmbedding()
    cache = SqliteVectorCache(tmp_path / "vectors.sqlite3", "fake-model")
    embedding = CachedEmbedding(inner, cache, "fake-model")

    texts = ["alpha", "beta"]
    embedding.encode(texts)
    assert inner.calls == 2

    # 同样的文本再编码一次，应全部命中缓存。
    embedding.encode(texts)
    assert inner.calls == 2
    assert embedding.hits == 2


def test_cache_invalidates_when_text_changes(tmp_path):
    inner = _CountingEmbedding()
    cache = SqliteVectorCache(tmp_path / "vectors.sqlite3", "fake-model")
    embedding = CachedEmbedding(inner, cache, "fake-model")

    embedding.encode(["alpha"])
    embedding.encode(["alpha changed"])
    assert inner.calls == 2
    assert cache.count() == 2


def test_cache_key_depends_on_model(tmp_path):
    assert cache_key("m1", "same text") != cache_key("m2", "same text")


def test_query_is_never_cached(tmp_path):
    inner = _CountingEmbedding()
    cache = SqliteVectorCache(tmp_path / "vectors.sqlite3", "fake-model")
    embedding = CachedEmbedding(inner, cache, "fake-model")

    embedding.encode(["how to"], is_query=True)
    embedding.encode(["how to"], is_query=True)
    assert inner.calls == 2
    assert cache.count() == 0


def test_hash_backend_ignores_cache_path(tmp_path):
    embedding = create_embedding("hash", cache_path=str(tmp_path / "v.sqlite3"))
    # RAG-P1-01：hash 后端不套 CachedEmbedding（哈希词袋成本极低，加缓存反增复杂度）
    # 检查 status 能正确拿到 hash 维度
    assert embedding.backend_status.backend_actual == "hash"
    assert embedding.backend_status.dimension == 256
