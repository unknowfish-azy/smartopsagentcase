"""给任意向量后端套一层持久化缓存。"""

from __future__ import annotations

from .base import EmbeddingModel
from .cache import SqliteVectorCache, cache_key


class CachedEmbedding(EmbeddingModel):
    """doc 向量命中缓存则跳过模型推理；query 永远现算。"""

    def __init__(
        self,
        inner: EmbeddingModel,
        cache: SqliteVectorCache,
        model_name: str,
    ) -> None:
        self.inner = inner
        self.cache = cache
        self.model_name = model_name
        self.hits = 0
        self.misses = 0

    def dimension(self) -> int:
        return self.inner.dimension()

    def encode(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> list[list[float]]:
        if is_query or not texts:
            return self.inner.encode(texts, is_query=is_query)

        keys = [cache_key(self.model_name, text) for text in texts]
        cached = self.cache.get_many(keys)

        missing_indexes = [
            index for index, key in enumerate(keys)
            if key not in cached
        ]

        if missing_indexes:
            vectors = self.inner.encode(
                [texts[index] for index in missing_indexes]
            )
            self.cache.put_many(
                [
                    (keys[index], vector)
                    for index, vector in zip(missing_indexes, vectors)
                ]
            )
            for index, vector in zip(missing_indexes, vectors):
                cached[keys[index]] = vector
            self.misses += len(missing_indexes)
        else:
            self.hits += len(keys)

        return [cached[key] for key in keys]


__all__ = ["CachedEmbedding"]
