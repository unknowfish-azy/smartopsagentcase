"""
SmartOpsAgent Knowledge Embedding Module.

提供知识库文本向量化能力：

- EmbeddingModel：Embedding 基础接口
- HashEmbedding：无需下载大模型的轻量级 Embedding
- SentenceTransformerEmbedding：基于 Sentence Transformers 的正式 Embedding 实现
"""

from .base import EmbeddingModel
from .hash_embedding import HashEmbedding

__all__ = [
    "EmbeddingModel",
    "HashEmbedding",
    "SentenceTransformerEmbedding",
]


def __getattr__(name: str):
    # SentenceTransformerEmbedding 依赖 sentence-transformers，
    # 导入时会尝试在线下载大模型，改为按需延迟导入，
    # 避免无网络 / 未安装依赖时直接崩溃。
    if name == "SentenceTransformerEmbedding":
        from .sentence_transformer import (
            SentenceTransformerEmbedding,
        )

        return SentenceTransformerEmbedding

    raise AttributeError(
        f"module {__name__!r} has no attribute {name!r}"
    )
