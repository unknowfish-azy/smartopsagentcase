"""基于 BGE（BERT 架构）的本地向量化实现。

不依赖 sentence-transformers，直接用 transformers + torch 加载本地缓存模型，
按 BGE 官方推荐的 CLS pooling + L2 归一化生成句向量，支持离线运行。

模型缺失或依赖不可用时抛 ``EmbeddingUnavailable``，由工厂回退到 HashEmbedding。
"""

from __future__ import annotations

import os
import threading
from typing import Any

from .base import EmbeddingModel, EmbeddingUnavailable

# BGE 中文模型检索时必须给 query 加这个指令前缀，doc 侧不加。
QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

# 模块级模型复用：同一进程内多个 BgeEmbedding 实例共享已加载的 tokenizer/model。
# 切换 BGE 为默认后，KnowledgeService 会被反复构造（尤其单测），
# 若不共享则每次都要从磁盘重载 ~90MB 权重，测试与启动都会退化。
_MODEL_CACHE: dict[tuple[str, str | None], tuple[Any, Any, int]] = {}
_CACHE_LOCK = threading.Lock()
# 推理锁：多个线程并发调用同一模型的 forward 时不安全（padding/batch 状态），串行化。
_INFER_LOCK = threading.Lock()


class BgeEmbedding(EmbeddingModel):
    """本地 BGE 向量化。

    首次加载约 1–2 秒，之后按 batch 推理；CPU 上 100 条短文本约几十毫秒。
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        *,
        max_length: int = 512,
        batch_size: int = 16,
        device: str | None = None,
    ) -> None:
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - 依赖缺失分支
            raise EmbeddingUnavailable(
                f"未安装 transformers/torch：{exc}"
            ) from exc

        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self._torch = torch

        # 优先离线加载本地缓存，避免无网环境长时间等待。
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        cache_key = (model_name, device)
        with _CACHE_LOCK:
            cached = _MODEL_CACHE.get(cache_key)
            if cached is None:
                try:
                    tokenizer = AutoTokenizer.from_pretrained(
                        model_name,
                        local_files_only=True,
                    )
                    model = AutoModel.from_pretrained(
                        model_name,
                        local_files_only=True,
                    )
                except Exception as exc:  # pragma: no cover - 模型缺失分支
                    raise EmbeddingUnavailable(
                        f"本地未找到模型 {model_name}：{exc}"
                    ) from exc

                if device:
                    model.to(device)
                model.eval()
                dimension = int(model.config.hidden_size)
                cached = (tokenizer, model, dimension)
                _MODEL_CACHE[cache_key] = cached

        self._tokenizer, self._model, self._dimension = cached

    def dimension(self) -> int:
        return self._dimension

    def encode(
        self,
        texts: list[str],
        *,
        is_query: bool = False,
    ) -> list[list[float]]:
        if not texts:
            return []

        payload = (
            [QUERY_INSTRUCTION + text for text in texts]
            if is_query
            else list(texts)
        )

        vectors: list[list[float]] = []
        torch = self._torch

        with _INFER_LOCK, torch.no_grad():
            for start in range(0, len(payload), self.batch_size):
                batch = payload[start:start + self.batch_size]
                inputs: dict[str, Any] = self._tokenizer(
                    batch,
                    padding=True,
                    truncation=True,
                    max_length=self.max_length,
                    return_tensors="pt",
                )
                outputs = self._model(**inputs)
                # BGE 用首 token（CLS）作为句向量。
                pooled = outputs.last_hidden_state[:, 0]
                pooled = torch.nn.functional.normalize(pooled, p=2, dim=1)
                vectors.extend(pooled.cpu().tolist())

        return vectors


__all__ = [
    "BgeEmbedding",
    "QUERY_INSTRUCTION",
]
