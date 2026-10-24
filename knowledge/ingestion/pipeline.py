import importlib.util
import sys
from pathlib import Path

from .chunker import TextChunker
from .metadata import enrich_chunk


def _load_parser_factory():
    """
    按需加载 document-parser 包并返回 ParserFactory。

    document-parser 目录名包含连字符，不符合 Python 包命名规范，
    无法通过标准 from-import 语句导入。这里借助 importlib 按文件
    路径将其注册为 knowledge.document_parser 包后再取 ParserFactory。
    """
    package_name = "knowledge.document_parser"

    module = sys.modules.get(package_name)
    if module is not None:
        return module.ParserFactory

    # knowledge/ingestion/pipeline.py -> 上级两级 = knowledge/
    knowledge_dir = Path(__file__).resolve().parent.parent
    parser_dir = knowledge_dir / "document-parser"

    spec = importlib.util.spec_from_file_location(
        package_name,
        parser_dir / "__init__.py",
        submodule_search_locations=[str(parser_dir)],
    )

    if spec is None or spec.loader is None:
        raise ImportError("无法加载 document-parser 包")

    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)

    return module.ParserFactory


class IngestionPipeline:

    def __init__(
        self,
        parser_factory=None,
        chunker: TextChunker | None = None,
    ):
        self.parser_factory = (
            parser_factory or _load_parser_factory()
        )
        self.chunker = chunker or TextChunker()

    def process(
        self,
        file_path: str,
        version: str = "latest",
    ):
        parser = self.parser_factory.get_parser(
            file_path
        )

        document = parser.parse(file_path)

        chunks = self.chunker.split(
            document_id=document.document_id,
            content=document.content,
            source=file_path,
            version=version,
        )

        for chunk in chunks:
            enrich_chunk(
                chunk,
                file_type=document.file_type,
                filename=document.filename,
            )

        return document, chunks
