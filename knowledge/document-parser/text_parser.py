from pathlib import Path
from uuid import uuid4

from .base import DocumentParser
from .models import ParsedDocument


class TextParser(DocumentParser):

    SUPPORTED = {
        ".txt",
        ".log",
        ".conf",
        ".yaml",
        ".yml",
        ".json",
        ".xml",
    }

    def supports(self, file_type: str) -> bool:
        return file_type.lower() in self.SUPPORTED

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)

        content = path.read_text(
            encoding="utf-8",
            errors="ignore",
        )

        return ParsedDocument(
            document_id=str(uuid4()),
            filename=path.name,
            content=content,
            file_type=path.suffix.lower(),
            metadata={
                "source": str(path),
            },
        )