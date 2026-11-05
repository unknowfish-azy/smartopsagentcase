"""端到端检索评测。

直接调用 ``KnowledgeService.search``（含 BM25 + 向量 + RRF + 重排），
判定口径优先 chunk_id，其次退回稳定的 source 前缀。
"""

from __future__ import annotations

import statistics
import time
from pathlib import Path

from .metrics import hit_at_k, mrr, ndcg_at_k, recall_at_k


def seed_corpus(
    service,
    root: Path,
    *,
    version: str = "reference",
) -> int:
    """把目录下的 md 语料批量写入服务，返回摄入篇数。"""
    documents = []

    for path in sorted(Path(root).rglob("*.md")):
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if not content.strip():
            continue

        documents.append(
            {
                "content": content,
                "source": f"reference/{path.relative_to(root)}",
                "version": version,
            }
        )

    service.add_documents(documents)
    return len(documents)


def _predicted(results, match_by: str) -> list[str]:
    # service.search 返回的是已序列化的 dict（chunk_id / source）。
    values = [
        item["chunk_id"] if match_by == "chunk" else item["source"]
        for item in results
    ]

    if match_by == "chunk":
        return values

    # 文档级判定：同一文档可能命中多个 chunk，去重只保留首次出现的位置，
    # 否则 nDCG 会把重复命中重复计分（超过 1.0）。
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped


def evaluate_service(
    service,
    cases,
    *,
    top_k: int = 5,
) -> dict:
    rows = []
    latencies = []

    for case in cases:
        match_by = "chunk" if case.expected_chunk_ids else "source"
        expected = (
            set(case.expected_chunk_ids)
            if match_by == "chunk"
            else set(case.expected_sources)
        )

        if not expected:
            continue

        started = time.perf_counter()
        payload = service.search(case.question, top_k=top_k)
        latencies.append((time.perf_counter() - started) * 1000)

        predicted = _predicted(payload["results"], match_by)

        rows.append(
            {
                "style": case.style,
                "hit": hit_at_k(predicted, expected, top_k),
                "recall": recall_at_k(predicted, expected, top_k),
                "mrr": mrr(predicted, expected),
                "ndcg": ndcg_at_k(predicted, expected, top_k),
            }
        )

    def _avg(items, key):
        return round(sum(item[key] for item in items) / len(items), 4) if items else 0.0

    summary = {
        "cases": len(rows),
        "hit@k": _avg(rows, "hit"),
        "recall@k": _avg(rows, "recall"),
        "mrr": _avg(rows, "mrr"),
        "ndcg@k": _avg(rows, "ndcg"),
        "latency_ms_avg": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "latency_ms_p50": round(statistics.median(latencies), 2) if latencies else 0.0,
        "by_style": {
            style: {
                "cases": len(group),
                "hit@k": _avg(group, "hit"),
                "recall@k": _avg(group, "recall"),
                "mrr": _avg(group, "mrr"),
                "ndcg@k": _avg(group, "ndcg"),
            }
            for style in sorted({row["style"] for row in rows})
            for group in [[row for row in rows if row["style"] == style]]
        },
    }

    return summary


__all__ = ["evaluate_service", "seed_corpus"]
