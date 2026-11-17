"""P1-3 故障案例检索服务。

- 加载 faiss index（case_index.faiss + case_index.npz）
- 用 EmbeddingService.encode(query) → cosine 检索
- 结果返回 incident_key/symptom/analysis/outcome/lesson

P2-3 扩展：learn() 把新案例 append 进索引 + 持久化 + 历史 jsonl 备份。
"""

from __future__ import annotations

import json
import time
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
    index_dir: Path | None = None


_state: _State | None = None


def init(index_dir: Path | None = None) -> _State:
    global _state
    state = _State()

    if index_dir is None:
        index_dir = Path(__file__).resolve().parents[3] / "data" / "models" / "case_retrieval"

    state.index_dir = Path(index_dir)
    index_file = state.index_dir / "case_index.faiss"
    meta_file = state.index_dir / "case_index.npz"

    if not index_file.exists() and not meta_file.exists():
        # 索引不存在 → 创建空索引（P2-3 learn 可以往里写）
        state.reason = f"case_index.faiss/.npz not found at {index_dir}, creating empty index"
        state.index_dir.mkdir(parents=True, exist_ok=True)
        emb = EmbeddingService()
        state.mode = emb.ensure_loaded()
        # 用 embedding 实际 dim 建索引
        dummy = emb.encode("init")[0]  # (D,)
        state.index = FaissIndexStore(dim=int(dummy.shape[0]))
        state.store_mode = state.index.vector_store_mode
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


# ---------------------------------------------------------------------------
# P1-3 retrieve
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# P2-3 learn（append + 持久化）
# ---------------------------------------------------------------------------

def has_incident_key(incident_key: str) -> bool:
    """查 incident_key 是否已在索引里（防重复）。"""
    state = get_state()
    if state.index is None:
        return False
    for m in state.index.meta:
        if m.get("incident_key") == incident_key:
            return True
    return False


def generate_incident_key(category: str, severity: str = "P2") -> str:
    """自动生成 incident_key：CATEGORY-YYYYMMDD-HHMMSS。"""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    cat_code = category.upper().replace("_", "-")[:8]
    return f"{cat_code}-{now.strftime('%Y%m%d-%H%M%S')}-{np.random.default_rng().integers(100, 999)}"


def learn(meta_dict: dict[str, Any]) -> dict[str, Any]:
    """把一个新案例 append 进 faiss 索引 + 持久化。

    meta_dict 字段（对齐 P1-3 训练脚本）：
      incident_key, category, severity, symptom, analysis, action_taken,
      outcome, lesson, recommendation, duration_minutes, created_at

    返回 dict: {ok, mode, index_size, incident_key, skipped}
    """
    state = get_state()
    if state.index is None:
        return {"ok": False, "mode": state.mode, "reason": "index 未初始化", "index_size": 0}

    incident_key = meta_dict.get("incident_key")
    if incident_key is None:
        incident_key = generate_incident_key(
            meta_dict.get("category", "other"),
            meta_dict.get("severity", "P2"),
        )
        meta_dict["incident_key"] = incident_key

    # 防重复
    if has_incident_key(incident_key):
        return {
            "ok": True,
            "mode": state.mode,
            "skipped": True,
            "reason": f"incident_key {incident_key} 已存在",
            "index_size": len(state.index),
            "incident_key": incident_key,
        }

    # ensure meta 里有 created_at
    meta_dict.setdefault("created_at", int(time.time()))

    # encode symptom + analysis 拼接做 embedding
    text_for_embed = (meta_dict.get("symptom", "") or "") + " " + (meta_dict.get("analysis", "") or "")
    emb = EmbeddingService()
    vec = emb.encode(text_for_embed)  # (1, D)

    # append
    state.index.add(vec, [meta_dict])

    # 持久化 faiss + npz
    if state.index_dir is not None:
        index_file = state.index_dir / "case_index.faiss"
        state.index.save(index_file)

        # 同时 append 一份到 history jsonl（独立备份）
        history_path = state.index_dir / "learn_history.jsonl"
        try:
            with open(history_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(meta_dict, ensure_ascii=False) + "\n")
        except Exception:
            pass  # jsonl 只是备份，faiss 才是主存储

    return {
        "ok": True,
        "mode": state.mode,
        "skipped": False,
        "index_size": len(state.index),
        "incident_key": incident_key,
    }


def get_index_size() -> int:
    state = get_state()
    return len(state.index) if state.index is not None else 0


def get_model_info() -> dict:
    state = get_state()
    # 统计 history jsonl 条数
    history_entries = 0
    if state.index_dir is not None:
        history_path = state.index_dir / "learn_history.jsonl"
        if history_path.exists():
            try:
                with open(history_path, "r", encoding="utf-8") as f:
                    history_entries = sum(1 for _ in f)
            except Exception:
                pass
    return {
        "available": state.index is not None,
        "kind": state.mode,
        "index_entries": len(state.index) if state.index is not None else 0,
        "index_store_mode": state.store_mode,
        "action_history_entries": history_entries,
        "store_path": str(state.index_dir) if state.index_dir else None,
        "reason": state.reason,
    }


# 向后兼容：暴露 retrieve/learn 都需要的 get_state
def _get_state_for_reflection() -> _State:
    return get_state()
