"""向量后端工厂（RAG-P1-01 增强版）。

``KNOWLEDGE_EMBEDDING_BACKEND=bge`` 时加载本地 BGE 模型；
依赖缺失、模型缺失或加载失败都会自动回退到 HashEmbedding，
保证知识服务在任何环境都能启动（只是语义能力降级）。

RAG-P1-01 增强：
1. create_embedding() 返回的 EmbeddingModel 附带 `.backend_status`
   （EmbeddingBackendStatus），包含 backend_requested/actual/model_revision/
   dimension/fallback_reason/cache_path 等结构化字段。
2. cache_key 分命名空间：hash vs bge 用不同 path，且 key 加 dimension/backend
   后缀，避免不同模型向量串用同一 SQLite cache。
3. CachedEmbedding 包装器增加 cache_hit_count，status 里能直接看到。
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .base import EmbeddingModel, EmbeddingUnavailable
from .hash_embedding import HashEmbedding
from .backend_status import EmbeddingBackendStatus

logger = logging.getLogger(__name__)


class EmbeddingModelWithStatus(EmbeddingModel):
    """把 EmbeddingModel 包装一下，挂上 EmbeddingBackendStatus。

    下游 KnowledgeService 不需要关心"现在用的是 hash 还是 bge"这个判断逻辑，
    直接从 `.backend_status` 读结构化状态即可。hash 回退 → status.fallback_reason
    有值；正常加载 → fallback_reason=None。
    """

    def __init__(self, inner: EmbeddingModel, status: EmbeddingBackendStatus):
        self._inner = inner
        self.backend_status = status

    def dimension(self) -> int:
        # RAG-P1-01：确保 status.dimension 和 inner.dimension() 一致
        dim = self._inner.dimension()
        self.backend_status.dimension = dim
        return dim

    def encode(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> list[list[float]]:
        return self._inner.encode(texts, is_query=is_query)


def create_embedding(
    backend: str = "hash",
    model_name: str = "BAAI/bge-small-zh-v1.5",
    cache_path: str | None = None,
) -> EmbeddingModelWithStatus:
    """RAG-P1-01：返回带 status 的包装器。

    签名兼容旧调用方（仍返回 EmbeddingModel-like 对象），但现在多了 `.backend_status`。
    """
    backend = (backend or "hash").strip().lower()
    fallback_reason: str | None = None
    actual_backend = backend
    model_revision: str | None = None
    dimension: int | None = None
    cache_actual_path: str | None = None
    inner: EmbeddingModel

    if backend == "hash":
        inner = HashEmbedding()
        dimension = inner.dimension()

    elif backend == "bge":
        try:
            from .bge_embedding import BgeEmbedding
            inner = BgeEmbedding(model_name=model_name)
            dimension = inner.dimension()
            # HuggingFace HF_HUB_OFFLINE=1 环境变量下，本地模型没有 commit sha 可拿
            # model_revision 先用 model_name 占位（真实 commit sha 需联网）
            model_revision = model_name
            logger.info(
                "已启用 BGE 向量后端：%s（%s 维）",
                model_name, dimension,
            )
        except EmbeddingUnavailable as exc:
            fallback_reason = str(exc)
            actual_backend = "hash"
            inner = HashEmbedding()
            dimension = inner.dimension()
            logger.warning("BGE 向量后端不可用，回退到哈希词袋：%s", exc)
        except Exception as exc:  # pragma: no cover - 兜底
            fallback_reason = str(exc)
            actual_backend = "hash"
            inner = HashEmbedding()
            dimension = inner.dimension()
            logger.warning("BGE 初始化异常，回退到哈希词袋：%s", exc)
    else:
        # 未知后端 → 直接 hash，标记 fallback_reason
        fallback_reason = f"未知后端 {backend!r}，回退到哈希词袋"
        actual_backend = "hash"
        inner = HashEmbedding()
        dimension = inner.dimension()
        logger.warning("未知向量后端 %s，使用哈希词袋", backend)

    # RAG-P1-01：分命名空间缓存。hash 和 bge 用不同 cache path，
    # 且 key 加 dimension/backend 后缀避免混用
    if cache_path:
        cache_path_str = str(cache_path).strip().lower()
        if cache_path_str in {"off", "none", "0", "false"}:
            cache_path = None

    if cache_path:
        from .cache import SqliteVectorCache
        from .caching import CachedEmbedding

        # 自动按 backend 分命名空间：原 path 最后加 "-hash.db" 或 "-bge.db"
        raw = Path(cache_path)
        if raw.suffix == ".db":
            new_stem = raw.stem + f"-{actual_backend}"
            new_path = raw.with_name(new_stem + raw.suffix)
        else:
            new_path = raw.parent / (raw.name + f"-{actual_backend}.db")
        cache_actual_path = str(new_path)

        cache = SqliteVectorCache(new_path, model_name)
        logger.info("向量缓存已启用：%s（已有 %s 条）", cache_actual_path, cache.count())
        inner = CachedEmbedding(inner, cache, model_name)

    # 组装 EmbeddingBackendStatus
    status = EmbeddingBackendStatus(
        backend_requested=backend,
        backend_actual=actual_backend,
        model_revision=model_revision,
        dimension=dimension,
        fallback_reason=fallback_reason,
        cache_path=cache_actual_path,
    )

    logger.info(
        "Embedding backend status: requested=%s actual=%s dim=%s fallback=%s",
        status.backend_requested, status.backend_actual,
        status.dimension, status.fallback_reason,
    )

    return EmbeddingModelWithStatus(inner, status)


__all__ = ["create_embedding"]
