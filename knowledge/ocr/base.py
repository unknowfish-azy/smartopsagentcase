from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class OCRBlock:
    text: str
    confidence: float | None = None
    left: int | None = None
    top: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class OCRResult:
    text: str
    blocks: list[OCRBlock] = field(default_factory=list)
    language: str = ""
    confidence: float | None = None
    engine: str = ""
    status: str = "SUCCEEDED"
    warnings: list[str] = field(default_factory=list)


class OCRService(ABC):

    @abstractmethod
    def extract_text(
        self,
        image_path: str,
    ) -> str:
        raise NotImplementedError

    def extract_document(self, image_path: str) -> OCRResult:
        return OCRResult(text=self.extract_text(image_path), engine=self.__class__.__name__)
