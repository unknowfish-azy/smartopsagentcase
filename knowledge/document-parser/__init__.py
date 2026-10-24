"""
SmartOpsAgent Knowledge Document Parser Module.

负责不同类型运维知识文档的统一解析入口。

支持的文档类型包括：
- TXT
- LOG
- CONF
- YAML / YML
- JSON
- XML
- Markdown
- PDF

注意：本目录名 document-parser 含有连字符，不符合 Python 包命名规范，
无法通过标准 import 语句直接导入。ingestion.pipeline 会通过 importlib
按文件路径将其注册为 knowledge.document_parser 后再使用。
"""

from .base import DocumentParser
from .models import ParsedDocument
from .text_parser import TextParser
from .markdown_parser import MarkdownParser
from .pdf_parser import PdfParser
from .parser_factory import ParserFactory

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "TextParser",
    "MarkdownParser",
    "PdfParser",
    "ParserFactory",
]
