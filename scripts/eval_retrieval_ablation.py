"""Retrieval ablation: BM25 / Vector / Hybrid / Hybrid+Rerank.

This script only *calls* the existing retrievers in knowledge/; it never tunes
their weights or search parameters. Every group is reported, including the
groups that lose, so the comparison stays honest and reproducible.

Usage:
    python scripts/eval_retrieval_ablation.py
    python scripts/eval_retrieval_ablation.py --query-set full   # 14 canonical + 42 rewrites
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from pathlib import Path
from typing import Any, Iterable

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.eval_retrieval import _SCENARIO_VARIANTS, extract_samples  # noqa: E402

GROUPS = ("A_bm25_only", "B_vector_only", "C_hybrid", "D_hybrid_rerank")


# --------------------------------------------------------------------------
# metrics
# --------------------------------------------------------------------------
def recall_at_k(rankings: Iterable[list[str]], expected: Iterable[str], k: int = 3) -> float:
    rows = list(zip(rankings, expected))
    if not rows:
        return 0.0
    return sum(1 for ranking, exp in rows if exp in ranking[:k]) / len(rows)


def mrr(rankings: Iterable[list[str]], expected: Iterable[str]) -> float:
    rows = list(zip(rankings, expected))
    if not rows:
        return 0.0
    total = 0.0
    for ranking, exp in rows:
        total += 1.0 / (ranking.index(exp) + 1) if exp in ranking else 0.0
    return total / len(rows)


def ndcg_at_k(rankings: Iterable[list[str]], expected: Iterable[str], k: int = 5) -> float:
    """Binary-gain nDCG@k: gain 1 if the expected chunk sits at that rank."""
    rows = list(zip(rankings, expected))
    if not rows:
        return 0.0
    total = 0.0
    for ranking, exp in rows:
        dcg = 0.0
        for position, doc_id in enumerate(ranking[:k], start=1):
            if doc_id == exp:
                dcg += 1.0 / math.log2(position + 1)
                break
        # exactly one relevant document exists, so IDCG = 1/log2(1+1) = 1.0
        total += dcg / 1.0
    return total / len(rows)


# --------------------------------------------------------------------------
# query set
# --------------------------------------------------------------------------
def build_query_set(data_dir: str | Path, query_set: str) -> list[tuple[str, str, str]]:
    """Return (sample_id, query, provenance) triples."""
    samples = extract_samples(data_dir)
    queries: list[tuple[str, str, str]] = []
    for sample in samples:
        queries.append((sample.sample_id, sample.instruction, "dataset:canonical"))
        if query_set == "full":
            for index, rewrite in enumerate(_SCENARIO_VARIANTS.get(sample.instruction, ()), 1):
                queries.append((sample.sample_id, rewrite, f"human-rewrite:{index}"))
    if query_set == "full":
        missing = sorted({sid for sid, _, prov in queries if prov == "dataset:canonical"}
                         - {sid for sid, _, prov in queries if prov.startswith("human-rewrite")})
        if missing:
            raise ValueError(f"human rewrites missing for samples: {missing}")
    return queries


# --------------------------------------------------------------------------
# ablation
# --------------------------------------------------------------------------
class _LegacyHashEmbedding:
    """Reproduces the pre-fix tokenizer (``str.split()``) for before/after comparison.

    Kept inside the evaluator so the source module stays untouched; used only by
    ``--legacy-tokenizer``.
    """

    def __init__(self, dimension: int = 256):
        self._dimension = dimension

    def encode(self, texts):
        import hashlib
        import math

        out = []
        for text in texts:
            vector = [0.0] * self._dimension
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                vector[int.from_bytes(digest[:4], "big") % self._dimension] += 1.0
            norm = math.sqrt(sum(x * x for x in vector))
            out.append(vector if norm == 0 else [x / norm for x in vector])
        return out


def build_index(data_dir: str | Path, legacy_tokenizer: bool = False):
    from knowledge.embedding.hash_embedding import HashEmbedding
    from knowledge.ingestion.chunker import TextChunker
    from knowledge.retrieval.bm25 import BM25Retriever
    from knowledge.retrieval.vector_store import InMemoryVectorStore

    samples = extract_samples(data_dir)
    chunker = TextChunker()
    embedding = _LegacyHashEmbedding() if legacy_tokenizer else HashEmbedding()
    chunks = []
    for sample in samples:
        chunk = chunker.split(sample.sample_id, sample.response, source=sample.source_file)[0]
        chunks.append(chunk)

    store = InMemoryVectorStore()
    for chunk, vector in zip(chunks, embedding.encode([c.content for c in chunks])):
        store.add(chunk, vector)
    bm25 = BM25Retriever(chunks)
    return samples, chunks, embedding, store, bm25


def run_group(group: str, query: str, embedding, store, bm25) -> list[str]:
    """Return ranked document ids for one query under one configuration."""
    from knowledge.reranker.lexical_reranker import LexicalReranker
    from knowledge.retrieval.hybrid import HybridRetriever

    if group == "A_bm25_only":
        return [r.document_id for r in bm25.search(query, top_k=5)]
    if group == "B_vector_only":
        return [r.document_id for r in store.search(embedding.encode([query])[0], top_k=5)]
    if group in ("C_hybrid", "D_hybrid_rerank"):
        hybrid = HybridRetriever(store, bm25)
        results = hybrid.search(query, embedding.encode([query])[0], top_k=10)
        if group == "D_hybrid_rerank":
            # rerank against a *copy* of the scores so group C stays untouched
            results = LexicalReranker().rerank(query, results, top_k=5)
        return [r.document_id for r in results[:5]]
    raise ValueError(f"unknown group: {group}")


def evaluate(data_dir: str | Path, output_csv: str | Path, query_set: str = "full",
             legacy_tokenizer: bool = False) -> dict[str, dict[str, float]]:
    samples, chunks, embedding, store, bm25 = build_index(data_dir, legacy_tokenizer)
    queries = build_query_set(data_dir, query_set)

    rows: list[dict[str, Any]] = []
    rankings: dict[str, list[list[str]]] = {g: [] for g in GROUPS}
    expected_by_group: dict[str, list[str]] = {g: [] for g in GROUPS}

    for sample_id, query, provenance in queries:
        for group in GROUPS:
            ranked = run_group(group, query, embedding, store, bm25)
            rankings[group].append(ranked)
            expected_by_group[group].append(sample_id)
            rank = ranked.index(sample_id) + 1 if sample_id in ranked else ""
            rows.append({
                "group": group,
                "sample_id": sample_id,
                "query_provenance": provenance,
                "query": query,
                "expected_document_id": sample_id,
                "hit_at_3": bool(rank and int(rank) <= 3),
                "rank": rank,
                "top5_document_ids": "|".join(ranked),
            })

    summary: dict[str, dict[str, float]] = {}
    for group in GROUPS:
        summary[group] = {
            "recall_at_3": recall_at_k(rankings[group], expected_by_group[group], 3),
            "mrr": mrr(rankings[group], expected_by_group[group]),
            "ndcg_at_5": ndcg_at_k(rankings[group], expected_by_group[group], 5),
            "n": len(rankings[group]),
        }

    output = Path(output_csv)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="SmartOps-Dataset/Linux")
    parser.add_argument("--output", default="06-工程整改/eval_retrieval_ablation.csv")
    parser.add_argument("--query-set", choices=("canonical", "full"), default="full",
                        help="canonical = 14 original questions; full = 14 + 42 human rewrites")
    parser.add_argument("--legacy-tokenizer", action="store_true",
                        help="reproduce the pre-fix str.split() tokenizer for before/after comparison")
    args = parser.parse_args(argv)

    try:
        summary = evaluate(args.data_dir, args.output, args.query_set, args.legacy_tokenizer)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(f"{'group':<16}{'n':>5}{'Recall@3':>11}{'MRR':>9}{'nDCG@5':>9}")
    for group in GROUPS:
        m = summary[group]
        print(f"{group:<16}{int(m['n']):>5}{m['recall_at_3']:>11.4f}{m['mrr']:>9.4f}{m['ndcg_at_5']:>9.4f}")
    best = max(GROUPS, key=lambda g: (summary[g]["recall_at_3"], summary[g]["mrr"]))
    print(f"\nbest by Recall@3: {best}")
    print(f"明细已写入：{Path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
