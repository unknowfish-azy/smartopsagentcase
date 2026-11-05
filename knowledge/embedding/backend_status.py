"""EmbeddingBackendStatus：RAG-P1-01 结构化后端状态。

工厂 create_embedding() 返回 EmbeddingModel 实例，但 RAG-P1-01 要求输出：
backend_requested / backend_actual / model_revision / dimension / fallback_reason
这样 KnowledgeService → server → /health 能看到"用了什么、为什么用、有没有回退"。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone


@dataclass
class EmbeddingBackendStatus:
    """RAG-P1-01：结构化后端状态。

    工厂 create_embedding() 不再只返回 EmbeddingModel，而是把 model
    包装在 EmbeddingModelWithStatus（见 factory.py）里，外部通过
    `.backend_status` 或 KnowledgeService.embedding_backend_status 拿到本对象。

    所有字段必须有值（允许 None），方便 JSON 序列化 + /health API 直接暴露。
    """
    backend_requested: str           # "hash" / "bge" / 未知值
    backend_actual: str               # 实际用的 "hash" / "bge"
    model_revision: str | None = None  # BGE: huggingface commit sha；hash: null
    dimension: int | None = None       # 256 (hash) / 384 (bge-small-zh) / ...
    fallback_reason: str | None = None  # null 表示没回退；否则是 Exception 消息
    cache_path: str | None = None       # SQLite cache 路径
    cache_hit_count: int = 0            # 来自 CachedEmbedding

    @property
    def has_fallback(self) -> bool:
        return self.backend_requested != self.backend_actual \
            or self.fallback_reason is not None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["has_fallback"] = self.has_fallback
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


@dataclass
class PersistenceManifest:
    """RAG-P1-01：持久化层 manifest（文档/chunk/embedding/scope/ACL/manifest）。

    任务书："先文档/chunk/embedding/scope/ACL/manifest 适配与重启恢复"。
    本 manifest 由 KnowledgeService 在持久化时写入 SQLite，重启时读取。
    版本化：不同 corpus 内容 / 不同 embedding backend / 不同 dimension 都
    必须换 manifest，避免混用不同模型的向量。
    """
    schema: str = "smartops.rag.manifest.v1"
    corpus_sha: str | None = None
    corpus_docs: int = 0
    corpus_chunks: int = 0
    embedding_backend: str = "hash"
    model_revision: str | None = None
    dimension: int = 256
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "PersistenceManifest":
        return cls(**{k: data.get(k) for k in cls.__dataclass_fields__})
