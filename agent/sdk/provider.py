from abc import ABC, abstractmethod
from typing import Any


class Provider(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def initialize(self, config: dict[str, Any]) -> None:
        raise NotImplementedError

    async def shutdown(self) -> None:
        return None