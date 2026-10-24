from abc import ABC, abstractmethod
from typing import Any


class Sandbox(ABC):

    @abstractmethod
    async def execute(
        self,
        action: str,
        **kwargs: Any,
    ) -> Any:
        raise NotImplementedError