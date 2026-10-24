from knowledge.embedding.hash_embedding import HashEmbedding
from knowledge.ingestion.chunker import TextChunker
from knowledge.retrieval.bm25 import BM25Retriever
from knowledge.retrieval.hybrid import HybridRetriever
from knowledge.retrieval.vector_store import InMemoryVectorStore


def test_hybrid_combines_vector_and_bm25_results():
    chunk = TextChunker().split("doc", "nginx upstream timeout", source="guide")[0]
    embedding = HashEmbedding()
    store = InMemoryVectorStore()
    store.add(chunk, embedding.encode([chunk.content])[0])
    result = HybridRetriever(store, BM25Retriever([chunk])).search("nginx timeout", embedding.encode(["nginx timeout"])[0])
    assert result
    assert result[0].retrieval_type == "hybrid"
