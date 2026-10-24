"""
SmartOpsAgent Knowledge Ingestion Module.

负责知识文档进入知识库前的预处理流程：

文档解析
    ↓
文本切块
    ↓
元数据补充
    ↓
生成 DocumentChunk
    ↓
交给 Embedding / Retrieval 模块
"""

from .models import DocumentChunk
from .chunker import TextChunker
from .metadata import enrich_chunk
from .pipeline import IngestionPipeline


__all__ = [
    "DocumentChunk",
    "TextChunker",
    "enrich_chunk",
    "IngestionPipeline",
]