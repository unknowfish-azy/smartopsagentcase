from pathlib import Path
from uuid import uuid4

from .base import DocumentParser
from .models import ParsedDocument


class PdfParser(DocumentParser):

    def supports(self, file_type: str) -> bool:
        return file_type.lower() == ".pdf"

    def parse(self, file_path: str) -> ParsedDocument:
        path = Path(file_path)

        # 延迟导入 pypdf，避免未安装时导致 document-parser 包整体无法导入。
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ImportError(
                "解析 PDF 需要安装 pypdf：pip install pypdf"
            ) from exc

        reader = PdfReader(str(path))

        pages = []

        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)

        content = "\n\n".join(pages)

        return ParsedDocument(
            document_id=str(uuid4()),
            filename=path.name,
            content=content,
            file_type=".pdf",
            metadata={
                "source": str(path),
                "pages": str(len(reader.pages)),
            },
        )