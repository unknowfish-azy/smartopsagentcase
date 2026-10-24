from knowledge.embedding.hash_embedding import HashEmbedding


def test_hash_embedding_is_normalized_and_deterministic():
    embedding = HashEmbedding(dimension=32)
    first = embedding.encode(["nginx timeout"])[0]
    second = embedding.encode(["nginx timeout"])[0]
    assert first == second
    assert round(sum(value * value for value in first), 6) == 1.0
