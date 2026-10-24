from abc import ABC, abstractmethod


class Reranker(ABC):

    @abstractmethod
    def rerank(
        self,
        query: str,
        results,
        top_k: int = 5,
    ):
        raise NotImplementedError