"""
SmartOpsAgent Knowledge Module.

知识库模块，负责文档摄入、向量/BM25 混合检索、
证据生成与可信度计算。

对外统一入口：KnowledgeService。
"""

from .service import KnowledgeService

__all__ = [
    "KnowledgeService",
]
