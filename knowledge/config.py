from dataclasses import dataclass


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


DEFAULT_CONFIG = KnowledgeConfig()