import math
import re

from .models import RetrievalResult


def tokenize(text: str) -> list[str]:
    return re.findall(
        r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+",
        text.lower(),
    )


class BM25Retriever:

    def __init__(
        self,
        chunks=None,
        k1: float = 1.5,
        b: float = 0.75,
    ):
        self.chunks = chunks or []
        self.k1 = k1
        self.b = b

        self.documents = [
            tokenize(chunk.content)
            for chunk in self.chunks
        ]

    def search(
        self,
        query: str,
        top_k: int = 10,
        version: str | None = None,
    ):

        query_tokens = tokenize(query)

        if not query_tokens:
            return []

        document_count = len(
            self.documents
        )

        if document_count == 0:
            return []

        avg_len = (
            sum(
                len(doc)
                for doc in self.documents
            )
            / document_count
        )

        document_frequency = {}

        for doc in self.documents:
            for token in set(doc):
                document_frequency[token] = (
                    document_frequency.get(token, 0)
                    + 1
                )

        results = []

        for index, doc in enumerate(
            self.documents
        ):

            chunk = self.chunks[index]

            if (
                version
                and version != "latest"
                and chunk.version != version
            ):
                continue

            score = 0.0
            doc_len = len(doc)

            for token in query_tokens:

                tf = doc.count(token)

                if tf == 0:
                    continue

                df = document_frequency.get(
                    token,
                    0,
                )

                idf = math.log(
                    1
                    + (
                        document_count - df + 0.5
                    )
                    / (
                        df + 0.5
                    )
                )

                numerator = (
                    tf * (self.k1 + 1)
                )

                denominator = (
                    tf
                    + self.k1
                    * (
                        1
                        - self.b
                        + self.b
                        * doc_len
                        / max(avg_len, 1)
                    )
                )

                score += (
                    idf
                    * numerator
                    / denominator
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
                    retrieval_type="bm25",
                )
            )

        results.sort(
            key=lambda x: x.score,
            reverse=True,
        )

        return results[:top_k]