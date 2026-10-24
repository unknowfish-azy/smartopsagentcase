from knowledge.reranker.lexical_reranker import LexicalReranker
from knowledge.retrieval.models import RetrievalResult


def test_reranker_prefers_token_overlap():
    results = [
        RetrievalResult("1", "redis memory usage", 0.5),
        RetrievalResult("2", "nginx upstream timeout", 0.5),
    ]
    ranked = LexicalReranker().rerank("nginx timeout", results)
    assert ranked[0].chunk_id == "2"
