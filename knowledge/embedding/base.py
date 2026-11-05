from abc import ABC, abstractmethod


class EmbeddingUnavailable(RuntimeError):
    """向量模型不可用（未安装依赖或本地无模型文件）。"""


class EmbeddingModel(ABC):

    @abstractmethod
    def encode(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> list[list[float]]:
        raise NotImplementedError

    @abstractmethod
    def dimension(self) -> int:
        raise NotImplementedError