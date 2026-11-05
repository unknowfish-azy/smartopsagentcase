from dataclasses import dataclass
import os
from pathlib import Path


def _env_str(name: str, default: str) -> str:
    value = os.getenv(name)
    return value.strip() if value and value.strip() else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if not value or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class KnowledgeConfig:
    chunk_size: int = 800
    chunk_overlap: int = 120

    top_k_vector: int = 10
    top_k_bm25: int = 10
    top_k_hybrid: int = 10
    top_k_rerank: int = 5

    vector_weight: float = 0.6
    bm25_weight: float = 0.4

    default_version: str = "latest"

    # 向量后端：bge = 本地 BGE 语义向量（默认），hash = 零依赖哈希词袋。
    # BGE 加载失败（依赖缺失 / 模型未缓存）时由工厂自动回退到 hash，
    # 回退原因记录在 EmbeddingBackendStatus.fallback_reason，/health 可见。
    # 需要强制零依赖模式时设 KNOWLEDGE_EMBEDDING_BACKEND=hash。
    embedding_backend: str = "bge"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"

    # 非 hash 后端的向量缓存路径；设为 "off" 可关闭。
    vector_cache_path: str = str(
        Path(__file__).resolve().parent / ".cache" / "vectors.sqlite3"
    )

    # TRUST-L3-P1-01：L3 受限 judge 一键开关。默认关闭（passthrough），
    # 关闭时不发起任何模型调用，不改变 L1/L2/L4 约束。
    l3_judge_enabled: bool = False
    l3_judge_timeout_ms: int = 800
    l3_judge_min_confidence: float = 0.6

    @classmethod
    def from_env(cls) -> "KnowledgeConfig":
        return cls(
            embedding_backend=_env_str(
                "KNOWLEDGE_EMBEDDING_BACKEND",
                "bge",
            ).lower(),
            embedding_model=_env_str(
                "KNOWLEDGE_EMBEDDING_MODEL",
                "BAAI/bge-small-zh-v1.5",
            ),
            vector_cache_path=_env_str(
                "KNOWLEDGE_VECTOR_CACHE",
                str(Path(__file__).resolve().parent / ".cache" / "vectors.sqlite3"),
            ),
            l3_judge_enabled=_env_bool("KNOWLEDGE_L3_JUDGE_ENABLED", False),
            l3_judge_timeout_ms=int(_env_str("KNOWLEDGE_L3_JUDGE_TIMEOUT_MS", "800")),
            l3_judge_min_confidence=float(
                _env_str("KNOWLEDGE_L3_JUDGE_MIN_CONFIDENCE", "0.6")
            ),
        )


DEFAULT_CONFIG = KnowledgeConfig()
