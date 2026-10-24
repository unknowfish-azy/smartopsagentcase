from abc import ABC, abstractmethod


class EmbeddingModel(ABC):

    @abstractmethod
    def encode(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError