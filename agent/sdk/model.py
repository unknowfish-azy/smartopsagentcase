from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ModelResponse:
    content: str
    model: str
    provider: str
    metadata: dict[str, Any]
    usage: dict[str, Any] = field(default_factory=dict)
    raw: Any = None


class ModelProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        **kwargs,
    ) -> ModelResponse:
        raise NotImplementedError