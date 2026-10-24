from knowledge.ingestion.chunker import TextChunker
from knowledge.retrieval.bm25 import BM25Retriever


def test_bm25_ranks_matching_terms():
    chunker = TextChunker()
    chunks = chunker.split("doc", "nginx upstream timeout", source="guide")
    chunks += chunker.split("doc2", "redis memory", source="guide")
    results = BM25Retriever(chunks).search("nginx timeout")
    assert results
    assert results[0].document_id == "doc"
