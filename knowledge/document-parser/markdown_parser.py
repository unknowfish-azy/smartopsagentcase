from pathlib import Path
from uuid import uuid4

from .base import DocumentParser
from .models import ParsedDocument


class MarkdownParser(DocumentParser):

    def supports(self, file_type: str) -> bool:
        return file_type.lower() == ".md"

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
            file_type=".md",
            metadata={
                "source": str(path),
            },
        )