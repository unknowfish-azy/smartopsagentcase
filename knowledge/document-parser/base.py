from abc import ABC, abstractmethod

from .models import ParsedDocument


class DocumentParser(ABC):

    @abstractmethod
    def supports(self, file_type: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def parse(self, file_path: str) -> ParsedDocument:
        raise NotImplementedError