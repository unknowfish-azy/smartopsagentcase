"""P1-3 故障案例检索服务。

- 加载 faiss index（case_index.faiss + case_index.npz）
- 用 EmbeddingService.encode(query) → cosine 检索
- 结果返回 incident_key/symptom/analysis/outcome/lesson
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from ..training.retrieval_model import (  # noqa: E402
    EmbeddingService,
    FaissIndexStore,
)


@dataclass
class _State:
    index: FaissIndexStore | None = None
    mode: str = "unavailable"       # "tinybert" | "tfidf" | "heuristic"
    store_mode: str = "none"        # "faiss" | "numpy" | "none"
    reason: str | None = None


_state: _State | None = None


def init(index_dir: Path | None = None) -> _State:
    global _state
    state = _State()

    if index_dir is None:
        index_dir = Path(__file__).resolve().parents[3] / "data" / "models" / "case_retrieval"

    index_file = Path(index_dir) / "case_index.faiss"
    meta_file = Path(index_dir) / "case_index.npz"

    if not index_file.exists() and not meta_file.exists():
        state.reason = f"case_index.faiss/.npz not found at {index_dir}"
        _state = state
        return state

    emb = EmbeddingService()
    state.mode = emb.ensure_loaded()
    state.index = FaissIndexStore.load(index_file)
    state.store_mode = state.index.vector_store_mode
    _state = state
    return state


def get_state() -> _State:
    global _state
    if _state is None:
        return init()
    return _state


def retrieve(query: str, top_k: int = 3, include_lesson: bool = True, include_recommendation: bool = True) -> dict:
    state = get_state()

    if state.index is None or len(state.index) == 0:
        return {
            "ok": True, "mode": state.mode, "index_entries": 0, "results": [],
        }

    emb = EmbeddingService()
    q_vec = emb.encode(query)

    hits = state.index.search(q_vec, top_k=top_k)
    results = []
    for h in hits:
        m = h["meta"]
        results.append({
            "rank": h["rank"],
            "score": round(h["score"], 4),
            "incident_key": m.get("incident_key", ""),
            "category": m.get("category", "unknown"),
            "severity": m.get("severity", ""),
            "symptom": m.get("symptom", ""),
            "outcome": m.get("outcome", ""),
            "lesson": m.get("lesson") if include_lesson else None,
            "recommendation": m.get("recommendation") if include_recommendation else None,
        })

    return {
        "ok": True,
        "mode": state.mode,
        "index_entries": len(state.index),
        "results": results,
    }


def get_model_info() -> dict:
    state = get_state()
    return {
        "available": state.index is not None and len(state.index) > 0,
        "kind": state.mode,
        "index_entries": len(state.index) if state.index is not None else 0,
        "index_store_mode": state.store_mode,
        "reason": state.reason,
    }
