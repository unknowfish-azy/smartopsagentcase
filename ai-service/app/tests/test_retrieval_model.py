"""TF-IDF 兜底模式的向量维度一致性。"""

import pytest

from app.training import retrieval_model as rm

pytestmark = pytest.mark.skipif(not rm._SKLEARN_VEC, reason="sklearn 未安装")


@pytest.fixture(autouse=True)
def _clean_vectorizer():
    rm.reset_tfidf_vectorizer()
    yield
    rm.reset_tfidf_vectorizer()


def _tfidf_service() -> "rm.EmbeddingService":
    """跳过模型加载，直接使用 tfidf 模式。"""
    service = rm.EmbeddingService()
    service._mode = "tfidf"
    service._model = object()  # ensure_loaded 见 _model 非空会提前返回
    return service


def test_tfidf_query_dimension_matches_index():
    """建索引与查询用不同实例时，词表必须共享，否则维度不一致会导致 faiss 断言失败。"""
    index_vectors = _tfidf_service().encode([
        "dns lookup failed nxdomain",
        "disk full on node",
        "high cpu usage on api",
    ])
    query_vector = _tfidf_service().encode(["dns lookup failed"])

    assert query_vector.shape == (1, index_vectors.shape[1])


def test_reset_tfidf_vectorizer_refits_new_vocabulary():
    first = _tfidf_service().encode(["alpha beta gamma"])

    rm.reset_tfidf_vectorizer()
    second = _tfidf_service().encode(["delta epsilon"])

    assert first.shape[1] != second.shape[1]


@pytest.mark.skipif(
    not (rm._TORCH_AVAILABLE and rm._TRANSFORMERS_AVAILABLE and rm._SKLEARN_VEC),
    reason="需要 torch/transformers/sklearn 才能触发降级路径",
)
def test_ensure_loaded_falls_back_to_tfidf_on_load_failure(monkeypatch):
    """HuggingFace 加载失败（如断网）时应降级到 tfidf，而不是抛异常。"""

    class _Broken:
        @staticmethod
        def from_pretrained(*args, **kwargs):
            raise RuntimeError("network unreachable")

    monkeypatch.setattr(rm, "BertTokenizerFast", _Broken)
    monkeypatch.setattr(rm, "BertModel", _Broken)

    service = rm.EmbeddingService()
    mode = service.ensure_loaded()

    assert mode == "tfidf"
    assert service._model is None

    vectors = service.encode(["dns lookup failed"])
    assert vectors.ndim == 2 and vectors.shape[0] == 1
