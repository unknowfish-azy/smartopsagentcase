"""
SmartOpsAgent Knowledge Retrieval Module.

负责知识库的多路检索与结果融合。

核心能力：
- RetrievalResult：统一检索结果模型
- cosine_similarity：向量相似度计算
- InMemoryVectorStore：向量检索
- BM25Retriever：关键词检索
- HybridRetriever：向量 + BM25 混合检索
- VersionFilter：知识版本过滤

典型检索流程：

Query
  ↓
Embedding
  ↓
┌───────────────┐
│               │
Vector          BM25
│               │
└───────┬───────┘
        ↓
     Hybrid
        ↓
Version Filter
        ↓
    Reranker
"""

from .models import RetrievalResult
from .vector_store import (
    InMemoryVectorStore,
    cosine_similarity,
)
from .bm25 import BM25Retriever
from .hybrid import HybridRetriever
from .version_filter import VersionFilter


__all__ = [
    "RetrievalResult",
    "InMemoryVectorStore",
    "cosine_similarity",
    "BM25Retriever",
    "HybridRetriever",
    "VersionFilter",
]