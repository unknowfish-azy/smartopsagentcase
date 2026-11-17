"""P1-3 故障案例向量检索：共享 embedding 类。

复用 P1-2 的 TinyBERT4Chinese backbone（同一模型文件，不重复下载），
取 CLS token 做文本 embedding，L2 normalize 后存 faiss IndexFlatIP。

设计：
- 全局单例 EmbeddingService（经验 578502：避免重复 from_pretrained）
- transformers/torch 缺失时 → TF-IDF + sklearn cosine 兜底
- faiss 缺失时 → 纯 numpy cosine 兜底
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# ---------------------------------------------------------------------------
# 依赖探测
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
_TRANSFORMERS_AVAILABLE = False
_FAISS_AVAILABLE = False
try:
    import torch  # type: ignore[import-untyped]
    try:
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
    except RuntimeError:
        pass  # 进程里 P1-2 已经调过，跳过
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None

try:
    from transformers import BertTokenizerFast, BertModel  # type: ignore[import-untyped]
    _TRANSFORMERS_AVAILABLE = True
except ImportError:
    BertTokenizerFast = None
    BertModel = None

try:
    import faiss  # type: ignore[import-untyped]
    _FAISS_AVAILABLE = True
except ImportError:
    faiss = None

try:
    from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
    from sklearn.metrics.pairwise import cosine_similarity  # type: ignore[import-untyped]
    _SKLEARN_VEC = True
except ImportError:
    TfidfVectorizer = None
    cosine_similarity = None
    _SKLEARN_VEC = False


# ---------------------------------------------------------------------------
# Embedding 服务（全局单例）
# ---------------------------------------------------------------------------

@dataclass
class EmbeddingService:
    """TinyBERT CLS token embedding service。"""

    model_name: str = "huawei-noah/TinyBERT_General_4L_312D"
    max_len: int = 64
    _tokenizer: Any = field(default=None, repr=False)
    _model: Any = field(default=None, repr=False)
    _mode: str = field(default="heuristic", repr=False)

    def ensure_loaded(self) -> str:
        """lazy load tokenizer + model，返回可用模式。"""
        if self._model is not None:
            return self._mode
        if _TORCH_AVAILABLE and _TRANSFORMERS_AVAILABLE:
            self._tokenizer = BertTokenizerFast.from_pretrained(self.model_name)
            self._model = BertModel.from_pretrained(self.model_name)
            self._model.eval()
            self._mode = "tinybert"
            return "tinybert"
        if _SKLEARN_VEC:
            self._mode = "tfidf"
            return "tfidf"
        self._mode = "heuristic"
        return "heuristic"

    def encode(self, texts: str | list[str]) -> np.ndarray:
        """编码文本 → (N, D) L2 normalized vectors。"""
        self.ensure_loaded()
        if isinstance(texts, str):
            texts = [texts]

        if self._mode == "tinybert":
            return self._encode_tinybert(texts)
        if self._mode == "tfidf":
            return self._encode_tfidf(texts)
        return self._encode_heuristic(texts)

    def _encode_tinybert(self, texts: list[str]) -> np.ndarray:
        enc = self._tokenizer(
            texts, padding=True, truncation=True,
            max_length=self.max_len, return_tensors="pt",
        )
        with torch.no_grad():
            out = self._model(enc["input_ids"], enc["attention_mask"])
            cls = out.last_hidden_state[:, 0, :].numpy()
        # L2 normalize for cosine
        norms = np.linalg.norm(cls, axis=1, keepdims=True) + 1e-9
        return cls / norms

    def _encode_tfidf(self, texts: list[str]) -> np.ndarray:
        # 每次新建（mock 规模小）；生产应缓存 fitted vectorizer
        vec = TfidfVectorizer(max_features=256, stop_words=None)
        mat = vec.fit_transform(texts).toarray().astype(np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9
        return mat / norms

    def _encode_heuristic(self, texts: list[str]) -> np.ndarray:
        """Bag-of-words over operational keywords（零依赖 fallback）。"""
        from .log_model import KEYWORD_VOCAB
        dim = len(KEYWORD_VOCAB) + 1
        out = np.zeros((len(texts), dim), dtype=np.float32)
        for i, text in enumerate(texts):
            low = text.lower()
            for kw, kid in KEYWORD_VOCAB.items():
                if kw in low:
                    out[i, kid] += 1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True) + 1e-9
        return out / norms


_embedding_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    global _embedding_service
    if _embedding_service is None:
        _embedding_service = EmbeddingService()
    return _embedding_service


# ---------------------------------------------------------------------------
# Faiss 索引（向量库）
# ---------------------------------------------------------------------------

class FaissIndexStore:
    """faiss IndexFlatIP（内积 = cosine after L2 normalize）。

    设计：
    - add(vectors, meta)：批量加向量 + 元数据（incident_key, outcome, lesson）
    - search(query_vec, top_k) → list[dict]
    - save(path) / load(path)：持久化到磁盘
    """

    def __init__(self, dim: int = 312):
        self.dim = dim
        self.index: Any = None
        self.meta: list[dict[str, Any]] = []  # 与 index 行对齐
        self.vector_store_mode: str = "none"
        if _FAISS_AVAILABLE:
            self.index = faiss.IndexFlatIP(dim)
            self.vector_store_mode = "faiss"
        else:
            self._numpy_vectors: np.ndarray | None = None
            self.vector_store_mode = "numpy"

    def add(self, vectors: np.ndarray, meta_batch: list[dict[str, Any]]) -> None:
        """批量加向量。vectors.shape=(N, D)"""
        if self.vector_store_mode == "faiss":
            self.index.add(vectors.astype(np.float32))
        else:
            if self._numpy_vectors is None:
                self._numpy_vectors = vectors.astype(np.float32)
            else:
                self._numpy_vectors = np.vstack([self._numpy_vectors, vectors.astype(np.float32)])
        self.meta.extend(meta_batch)

    def search(self, query_vec: np.ndarray, top_k: int = 3) -> list[dict[str, Any]]:
        """query_vec: (1, D) or (D,) → 返回 top-k 候选。"""
        q = query_vec.reshape(1, -1).astype(np.float32)
        results: list[dict[str, Any]] = []

        if self.vector_store_mode == "faiss" and self.index is not None:
            if self.index.ntotal == 0:
                return results
            k = min(top_k, self.index.ntotal)
            scores, ids = self.index.search(q, k)
            for score, idx in zip(scores[0], ids[0]):
                if idx < 0 or idx >= len(self.meta):
                    continue
                results.append({
                    "score": float(score),
                    "rank": len(results) + 1,
                    "meta": self.meta[idx],
                })
        else:
            if self._numpy_vectors is None or len(self._numpy_vectors) == 0:
                return results
            sims = (self._numpy_vectors @ q.T).flatten()
            ranked = np.argsort(-sims)[:top_k]
            for rank_pos, idx in enumerate(ranked, start=1):
                results.append({
                    "score": float(sims[idx]),
                    "rank": rank_pos,
                    "meta": self.meta[idx],
                })

        return results

    def __len__(self) -> int:
        if self.vector_store_mode == "faiss" and self.index is not None:
            return self.index.ntotal
        return len(self.meta)

    def save(self, path: Path) -> None:
        """持久化：meta + numpy vectors 存 .npz，faiss index 存单独文件。"""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        meta_path = path.with_suffix(".npz")

        # 提取向量（numpy 方式，不依赖 faiss vector_to_array）
        if self.vector_store_mode == "faiss" and self.index is not None:
            ntotal = self.index.ntotal
            if ntotal > 0:
                # 用 index.reconstruct 逐行重建（兼容所有 faiss 版本）
                dim = self.index.d
                vectors = np.zeros((ntotal, dim), dtype=np.float32)
                for i in range(ntotal):
                    vectors[i] = self.index.reconstruct(i)
            else:
                vectors = np.zeros((0, self.dim), dtype=np.float32)
        else:
            vectors = self._numpy_vectors if self._numpy_vectors is not None else np.zeros((0, self.dim), dtype=np.float32)

        np.savez(
            str(meta_path),
            meta=np.array(self.meta, dtype=object),
            vectors=vectors,
            store_mode=self.vector_store_mode,
        )

        # faiss index 单独写（存路径本身就是 faiss 文件）
        if self.vector_store_mode == "faiss" and self.index is not None and _FAISS_AVAILABLE:
            faiss.write_index(self.index, str(path))

    @classmethod
    def load(cls, path: Path) -> "FaissIndexStore":
        path = Path(path)
        meta_path = path.with_suffix(".npz")
        store = cls()
        if not meta_path.exists():
            return store

        data = np.load(str(meta_path), allow_pickle=True)
        store._numpy_vectors = data["vectors"]
        store.meta = list(data["meta"])
        store.vector_store_mode = str(data.get("store_mode", "numpy"))
        store.dim = store._numpy_vectors.shape[1] if len(store._numpy_vectors) > 0 else store.dim

        # 如果有 faiss index 文件且 faiss 可用，加载它
        if path.exists() and _FAISS_AVAILABLE:
            try:
                store.index = faiss.read_index(str(path))
                store.vector_store_mode = "faiss"
            except Exception:
                store.index = None
                store.vector_store_mode = "numpy"

        return store
