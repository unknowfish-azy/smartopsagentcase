import math

from .models import RetrievalResult


def cosine_similarity(
    a: list[float],
    b: list[float],
) -> float:

    if not a or not b:
        return 0.0

    numerator = sum(
        x * y
        for x, y in zip(a, b)
    )

    norm_a = math.sqrt(
        sum(x * x for x in a)
    )

    norm_b = math.sqrt(
        sum(x * x for x in b)
    )

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return numerator / (norm_a * norm_b)


class InMemoryVectorStore:

    def __init__(self):
        self.items = []

    def add(
        self,
        chunk,
        vector: list[float],
    ):
        self.items.append(
            {
                "chunk": chunk,
                "vector": vector,
            }
        )

    def search(
        self,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ) -> list[RetrievalResult]:

        results = []

        for item in self.items:

            chunk = item["chunk"]

            if (
                version
                and chunk.version != version
                and version != "latest"
            ):
                continue

            score = cosine_similarity(
                query_vector,
                item["vector"],
            )

            results.append(
                RetrievalResult(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    content=chunk.content,
                    score=score,
                    source=chunk.source,
                    version=chunk.version,
                    metadata=chunk.metadata,
                    retrieval_type="vector",
                )
            )

        results.sort(
            key=lambda x: x.score,
            reverse=True,
        )

        return results[:top_k]