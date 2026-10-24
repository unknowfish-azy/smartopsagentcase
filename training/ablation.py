"""Declared ablation matrix; execution is intentionally separate."""

from __future__ import annotations


RAG_ABLATIONS = (
    "VECTOR", "BM25", "HYBRID", "HYBRID_RERANKER",
    "HYBRID_RERANKER_VERSION", "HYBRID_RERANKER_VERSION_EVIDENCE",
)
INSPECTOR_ABLATIONS = (
    "AGENT", "RULE_INSPECTOR", "RULE_EVIDENCE_INSPECTOR",
    "RULE_EVIDENCE_AI_JUDGE", "FULL_INSPECTOR_VERIFICATION",
)


def not_run_plan() -> dict:
    return {
        "status": "NOT RUN",
        "rag": [{"name": name, "metrics": None} for name in RAG_ABLATIONS],
        "inspector": [{"name": name, "metrics": None} for name in INSPECTOR_ABLATIONS],
    }


__all__ = ["INSPECTOR_ABLATIONS", "RAG_ABLATIONS", "not_run_plan"]
