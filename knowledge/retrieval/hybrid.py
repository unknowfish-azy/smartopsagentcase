from .models import RetrievalResult


class HybridRetriever:

    def __init__(
        self,
        vector_store,
        bm25_retriever,
        vector_weight: float = 0.6,
        bm25_weight: float = 0.4,
    ):
        self.vector_store = vector_store
        self.bm25_retriever = bm25_retriever

        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight

    @staticmethod
    def _normalize(results):

        if not results:
            return {}

        max_score = max(
            result.score
            for result in results
        )

        if max_score <= 0:
            return {
                result.chunk_id: 0.0
                for result in results
            }

        return {
            result.chunk_id: result.score / max_score
            for result in results
        }

    def search(
        self,
        query: str,
        query_vector: list[float],
        top_k: int = 10,
        version: str | None = None,
    ):

        vector_results = (
            self.vector_store.search(
                query_vector=query_vector,
                top_k=top_k,
                version=version,
            )
        )

        bm25_results = (
            self.bm25_retriever.search(
                query=query,
                top_k=top_k,
                version=version,
            )
        )

        vector_scores = (
            self._normalize(
                vector_results
            )
        )

        bm25_scores = (
            self._normalize(
                bm25_results
            )
        )

        all_results = {}

        for result in (
            vector_results
            + bm25_results
        ):
            all_results[result.chunk_id] = result

        merged = []

        for chunk_id, result in all_results.items():

            score = (
                self.vector_weight
                * vector_scores.get(
                    chunk_id,
                    0.0,
                )
                +
                self.bm25_weight
                * bm25_scores.get(
                    chunk_id,
                    0.0,
                )
            )

            merged.append(
                RetrievalResult(
                    chunk_id=result.chunk_id,
                    document_id=result.document_id,
                    content=result.content,
                    score=score,
                    source=result.source,
                    version=result.version,
                    metadata=result.metadata,
                    retrieval_type="hybrid",
                )
            )

        merged.sort(
            key=lambda x: x.score,
            reverse=True,
        )

        return merged[:top_k]