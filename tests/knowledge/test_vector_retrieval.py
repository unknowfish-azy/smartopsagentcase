from knowledge.embedding.hash_embedding import HashEmbedding
from knowledge.ingestion.chunker import TextChunker
from knowledge.retrieval.vector_store import InMemoryVectorStore


def test_vector_retrieval_returns_matching_version():
    chunker = TextChunker()
    chunks = chunker.split("doc", "nginx upstream timeout", source="guide", version="1.24")
    store = InMemoryVectorStore()
    store.add(chunks[0], HashEmbedding().encode([chunks[0].content])[0])
    result = store.search(HashEmbedding().encode(["nginx timeout"])[0], version="1.24")
    assert len(result) == 1
    assert result[0].retrieval_type == "vector"
