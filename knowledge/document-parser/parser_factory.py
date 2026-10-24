from pathlib import Path

from .base import DocumentParser
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .text_parser import TextParser


class ParserFactory:

    def __init__(self):
        self.parsers: list[DocumentParser] = [
            TextParser(),
            MarkdownParser(),
            PdfParser(),
        ]

    def get_parser(self, file_path: str) -> DocumentParser:
        suffix = Path(file_path).suffix.lower()

        for parser in self.parsers:
            if parser.supports(suffix):
                return parser

        raise ValueError(
            f"不支持的文件类型: {suffix}"
        )